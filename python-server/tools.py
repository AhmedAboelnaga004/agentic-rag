import os

from langchain_core.tools import tool
from langchain_pinecone import PineconeVectorStore, PineconeEmbeddings

# Module-level cache so the vector store is only initialised once per process
_vector_store: PineconeVectorStore | None = None


def get_vector_store() -> PineconeVectorStore:
    """
    Lazily initialise and cache the Pinecone vector store.
    The embedding model MUST match the one used during ingestion.
    """
    global _vector_store
    if _vector_store is not None:
        return _vector_store

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

    _vector_store = PineconeVectorStore(
        index_name=index_name,
        embedding=embeddings,
        pinecone_api_key=api_key,
    )
    return _vector_store


@tool
def search_knowledge_base(query: str) -> str:
    """
    Searches the internal knowledge base for technical info and documentation.
    Use this when you need to find information from uploaded PDF documents.

    Args:
        query: The search query to look up in the knowledge base.
    """
    print(f'[Tool] Searching Pinecone for: "{query}"')

    store = get_vector_store()

    # Fetch the top 10 most semantically similar chunks
    results = store.similarity_search(query, k=10)

    for i, r in enumerate(results):
        print(f"Result {i + 1}:", r.page_content[:200])

    if not results:
        return "No relevant information found in the knowledge base."

    # Return all chunks as one context block separated by dividers
    return "\n\n---\n\n".join(doc.page_content for doc in results)
