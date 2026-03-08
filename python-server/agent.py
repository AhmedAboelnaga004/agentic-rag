import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.chat_history import InMemoryChatMessageHistory
from tools import search_knowledge_base

# In-memory conversation store: { session_id -> InMemoryChatMessageHistory }
_session_histories: dict[str, InMemoryChatMessageHistory] = {}

SYSTEM_PROMPT = (
    "You are a helpful AI assistant with access to a knowledge base. "
    "When users ask questions, search the knowledge base using the available tools YOU SHOULD SEARCH IN THE KNOWLEDGE BASE FIRST, before trying to answer, to ensure you have the most accurate and up-to-date information. "
    "to find relevant information. Be concise and accurate."
)

TOOLS = [search_knowledge_base]


def _get_history(session_id: str) -> InMemoryChatMessageHistory:
    if session_id not in _session_histories:
        _session_histories[session_id] = InMemoryChatMessageHistory()
    return _session_histories[session_id]


async def run_agent(message: str, session_id: str = "default") -> str:
    """
    Run the ReAct agent for a given user message.
    Maintains per-session conversation history via an in-memory store.
    """
    print(f'[Agent] Running for: "{message}"')

    # Build the LLM
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=os.environ["GOOGLE_API_KEY"],
        temperature=1.0,
    )

    # Bind tools so the LLM can call them
    llm_with_tools = llm.bind_tools(TOOLS)

    # Get this session's history
    history = _get_history(session_id)

    # Build message list: system + history + new user message
    messages = (
        [{"role": "system", "content": SYSTEM_PROMPT}]
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
            matched_tool = next((t for t in TOOLS if t.name == tool_name), None)
            if matched_tool:
                tool_result = matched_tool.invoke(tool_args)
            else:
                tool_result = f"Tool '{tool_name}' not found."

            messages.append({
                "role": "tool",
                "content": str(tool_result),
                "tool_call_id": tc["id"],
            })

    # Persist the exchange in history
    history.add_user_message(message)
    history.add_ai_message(str(output))

    print(f"[Agent] Response: {str(output)[:100]}...")
    return str(output)
