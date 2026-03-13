import os

from langchain_core.tools import tool
from langchain_pinecone import PineconeVectorStore, PineconeEmbeddings

# ── Namespace-aware vector store factory ─────────────────────────────────────
# Namespace must come from database (courses -> universities), never user input.
# We cache one store per namespace so we don't re-initialise on every call.
_store_cache: dict[str, PineconeVectorStore] = {}


def get_vector_store(namespace: str) -> PineconeVectorStore:
    """
    Return (and cache) a PineconeVectorStore scoped to the given
    namespace.  The embedding model MUST match the one used during ingestion.
    """
    if namespace in _store_cache:
        return _store_cache[namespace]

    api_key = os.environ.get("PINECONE_API_KEY")
    index_name = os.environ.get("PINECONE_INDEX")

    if not api_key:
        raise ValueError("Missing PINECONE_API_KEY environment variable")
    if not index_name:
        raise ValueError("Missing PINECONE_INDEX environment variable")

    embeddings = PineconeEmbeddings(
        model="llama-text-embed-v2",
        pinecone_api_key=api_key,
    )

    store = PineconeVectorStore(
        index_name=index_name,
        embedding=embeddings,
        pinecone_api_key=api_key,
        namespace=namespace,
    )
    _store_cache[namespace] = store
    return store


@tool
def search_knowledge_base(query: str, namespace: str, course_id: str) -> str:
    """
    Broad semantic search within a specific namespace, always
    filtered to a single course.  Use this for general or open-ended questions
    where no specific section heading or content type is mentioned.

    Args:
        query:         The search query.
        namespace:     Pinecone namespace fetched from database.
        course_id:     Course identifier — always applied as a mandatory filter
                       so results never bleed across courses.
    """
    print(f'[Tool] Broad search | ns={namespace} | course={course_id} | query="{query}"')

    store = get_vector_store(namespace)
    results = store.similarity_search(
        query,
        k=10,
        filter={"course_id": {"$eq": course_id}},
    )

    for i, r in enumerate(results):
        print(f"  Result {i + 1}:", r.page_content[:200])

    if not results:
        return "No relevant information found in the knowledge base for this course."

    return "\n\n---\n\n".join(doc.page_content for doc in results)


@tool
def search_knowledge_base_filtered(
    query: str,
    namespace: str,
    course_id: str,
    section_heading: str | None = None,
    content_type: str | None = None,
    has_formula: bool | None = None,
) -> str:
    """
    Targeted semantic search within a specific namespace, always
    filtered to a single course, with optional additional filters.
    Use this when the user mentions a specific section, lecture heading,
    or content type (e.g. 'examples from Lecture 3', 'all formulas in Chapter 2').

    IMPORTANT — additional filter values must match stored metadata exactly:
      • section_heading: e.g. "Lecture 3: Inverse Trig > Examples"
      • content_type: one of "formula", "table", "visual", "definition",
        "example", "explanation"
      • has_formula: true to restrict to chunks that contain math expressions
    Pass only the optional filters you are confident about; leave the rest as None.

    Args:
        query:           The search query (semantic similarity).
        namespace:       Pinecone namespace fetched from database.
        course_id:       Course identifier — always applied as a mandatory filter.
        section_heading: Exact section heading string stored in chunk metadata.
        content_type:    Content classification stored in chunk metadata.
        has_formula:     If true, restrict to math-heavy chunks.
    """
    print(
        f'[Tool] Filtered search | ns={namespace} | course={course_id} | '
        f'section={section_heading} | type={content_type} | formula={has_formula} | '
        f'query="{query}"'
    )

    store = get_vector_store(namespace)

    # course_id is ALWAYS enforced — it is not optional
    filter_dict: dict = {"course_id": {"$eq": course_id}}
    if section_heading is not None:
        filter_dict["section_heading"] = {"$eq": section_heading}
    if content_type is not None:
        filter_dict["content_type"] = {"$eq": content_type}
    if has_formula is not None:
        filter_dict["has_formula"] = {"$eq": has_formula}

    results = store.similarity_search(query, k=10, filter=filter_dict)

    for i, r in enumerate(results):
        print(f"  Result {i + 1}:", r.page_content[:200])

    if not results:
        return (
            "No results found with the given filters. "
            "Try relaxing the optional filters or use search_knowledge_base for a broader search."
        )

    # Prepend a metadata header to each chunk so the LLM can cite sources
    parts = []
    for doc in results:
        meta = doc.metadata
        header_parts = []
        if meta.get("course_code"):
            header_parts.append(f"Course: {meta['course_code']}")
        if meta.get("section_heading"):
            header_parts.append(f"Section: {meta['section_heading']}")
        if meta.get("content_type"):
            header_parts.append(f"Type: {meta['content_type']}")
        if meta.get("page") is not None:
            header_parts.append(f"Page: {meta['page']}")
        header = " | ".join(header_parts)
        parts.append(f"[{header}]\n{doc.page_content}" if header else doc.page_content)

    return "\n\n---\n\n".join(parts)
