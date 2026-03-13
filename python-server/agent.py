import os
from functools import partial
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.chat_history import InMemoryChatMessageHistory
from tools import search_knowledge_base, search_knowledge_base_filtered
import database

# In-memory conversation store: { session_id -> InMemoryChatMessageHistory }
_session_histories: dict[str, InMemoryChatMessageHistory] = {}

# Module-level LLM instance — built once on first import, reused on every request.
# Avoids ~200-400ms cold-init overhead per call.
_llm: ChatGoogleGenerativeAI | None = None


def _get_llm() -> ChatGoogleGenerativeAI:
    global _llm
    if _llm is None:
        _llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=os.environ["GOOGLE_API_KEY"],
            temperature=0,
        )
    return _llm


def _build_system_prompt(course_name: str, course_id: str) -> str:
    """
    Build a per-call system prompt that locks the agent to one course.
    Both the prompt-level restriction (graceful refusal) and the tool-level
    filter (code enforcement) work together to prevent cross-course answers.
    """
    return (
        f"You are the AI study assistant for {course_name} (ID: {course_id}).\n\n"
        "RULES YOU MUST FOLLOW WITHOUT EXCEPTION:\n"
        f"1. You ONLY answer questions about {course_name}. "
        "If the student asks about any other subject, a different course, or anything "
        f"unrelated to {course_name}, politely decline and tell them you can only help "
        f"with {course_name}.\n"
        "2. ALWAYS search the knowledge base before answering — never rely on prior "
        "knowledge alone.\n"
        "3. You have two search tools:\n"
        "   • search_course — use for general or open-ended questions.\n"
        "   • search_course_filtered — use when the student mentions a specific "
        "section, lecture, or content type (e.g. 'examples from Lecture 3', "
        "'all formulas in Chapter 2'). Populate only the optional filters you are "
        "confident about; leave the rest as null.\n"
        "4. Both tools are already locked to this course — you do NOT need to specify "
        "the course yourself.\n"
        "5. Always cite the section heading and page number when available in your answer.\n\n"
        "MATH FORMATTING RULES — follow these exactly:\n"
        "6. ALL mathematical expressions MUST be written in LaTeX. "
        "Use $...$ for inline math and $$...$$ for display/block equations. "
        "Never write math as plain text (e.g. never write 'e^cos-1(4x)', "
        "always write $e^{\\cos^{-1}(4x)}$).\n"
        "7. Use a SINGLE backslash for LaTeX commands (\\frac, \\sqrt, \\cdot, etc.). "
        "Do NOT double-escape backslashes (never write \\\\frac or \\\\cdot).\n"
        "8. When explaining a derivation step by step, write each step as its own "
        "display equation on a new line using $$...$$.\n"
        "9. Do NOT restate the original question in plain text before answering. "
        "Go directly to the explanation."
    )


# Cache bound tool lists per (namespace, course_id) so @tool schema
# introspection and partial application only happen once per course.
_tools_cache: dict[tuple[str, str], list] = {}


def _make_course_tools(namespace: str, course_id: str):
    """
    Return LangChain tool objects with namespace and course_id pre-filled
    via partial application.  The LLM only sees and fills the remaining args
    (query + optional filters), so it can never hallucinate identity fields.
    Results are cached per (namespace, course_id) pair.
    """
    cache_key = (namespace, course_id)
    if cache_key in _tools_cache:
        return _tools_cache[cache_key]
    # Wrap the underlying functions with the identity fields baked in
    _broad_fn = partial(
        search_knowledge_base.func,
        namespace=namespace,
        course_id=course_id,
    )
    _filtered_fn = partial(
        search_knowledge_base_filtered.func,
        namespace=namespace,
        course_id=course_id,
    )

    @tool
    def search_course(query: str) -> str:
        """
        Broad semantic search in this course's knowledge base.
        Use for general or open-ended questions about the course material.

        Args:
            query: What to search for.
        """
        return _broad_fn(query=query)

    @tool
    def search_course_filtered(
        query: str,
        section_heading: str | None = None,
        content_type: str | None = None,
        has_formula: bool | None = None,
    ) -> str:
        """
        Targeted semantic search in this course's knowledge base with optional filters.
        Use when the student mentions a specific section, lecture heading, or content type.

        Filter values must match stored metadata exactly:
          • section_heading: e.g. "Lecture 3: Inverse Trig > Examples"
          • content_type: "formula" | "table" | "visual" | "definition" | "example" | "explanation"
          • has_formula: true to restrict to chunks containing math expressions

        Args:
            query:           What to search for.
            section_heading: Exact section heading from the document.
            content_type:    Type of content to filter by.
            has_formula:     Set true to find math-heavy chunks.
        """
        return _filtered_fn(
            query=query,
            section_heading=section_heading,
            content_type=content_type,
            has_formula=has_formula,
        )

    _tools_cache[cache_key] = [search_course, search_course_filtered]
    return _tools_cache[cache_key]


async def _get_history(session_id: str) -> InMemoryChatMessageHistory:
    """
    Return in-memory history for this session.
    On first access, load persisted messages from Postgres so history
    survives server restarts.  Subsequent accesses hit the in-memory cache.
    """
    if session_id not in _session_histories:
        hist = InMemoryChatMessageHistory()
        # Replay persisted messages into in-memory history
        rows = await database.load_session_messages(session_id)
        for row in rows:
            if row["role"] == "human":
                hist.add_user_message(row["content"])
            else:
                hist.add_ai_message(row["content"])
        _session_histories[session_id] = hist
    return _session_histories[session_id]


async def run_agent(
    message: str,
    session_id: str = "default",
    *,
    namespace: str,
    course_id: str,
    course_name: str,
) -> str:
    """
    Run the course-locked ReAct agent for a given student message.
    The agent can only search within the student's course (enforced at both
    prompt level and tool level).  Conversation history is kept per session.
    """
    print(f'[Agent] ns={namespace} | course={course_id} | message="{message}"')

    # Reuse the cached LLM instance (built once per process)
    llm = _get_llm()

    # Build course-locked tools (cached per namespace+course pair)
    tools = _make_course_tools(namespace=namespace, course_id=course_id)
    llm_with_tools = llm.bind_tools(tools)

    # Build dynamic per-call system prompt
    system_prompt = _build_system_prompt(course_name=course_name, course_id=course_id)

    # Get this session's history (loads from Postgres on first access)
    history = await _get_history(session_id)

    # Build message list: system + history + new user message
    messages = (
        [{"role": "system", "content": system_prompt}]
        + [{"role": m.type, "content": m.content} for m in history.messages]
        + [{"role": "user", "content": message}]
    )

    # Agentic loop: keep calling the LLM until it stops issuing tool calls
    while True:
        response = await llm_with_tools.ainvoke(messages)

        # If no tool calls → final answer
        if not response.tool_calls:
            raw = response.content
            # Gemini sometimes returns a list of content blocks instead of a plain string
            if isinstance(raw, list):
                output = " ".join(
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in raw
                ).strip()
            else:
                output = raw or ""
            break

        # Execute each tool call and append results to the message list
        messages.append(response)
        for tc in response.tool_calls:
            tool_name = tc["name"]
            tool_args = tc["args"]

            # Find and call the matching tool
            matched_tool = next((t for t in tools if t.name == tool_name), None)
            if matched_tool:
                tool_result = matched_tool.invoke(tool_args)
            else:
                tool_result = f"Tool '{tool_name}' not found."

            messages.append({
                "role": "tool",
                "content": str(tool_result),
                "tool_call_id": tc["id"],
            })

    # Update in-memory history immediately so the next turn in the same
    # session sees the new messages without waiting for the background write.
    history.add_user_message(message)
    history.add_ai_message(str(output))
    # (Postgres persistence is handled by the BackgroundTask in main.py)

    print(f"[Agent] Response: {str(output)[:100]}...")
    return str(output)
