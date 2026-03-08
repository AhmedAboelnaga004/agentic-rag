import os
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_pinecone import PineconeVectorStore, PineconeEmbeddings
from pinecone import Pinecone

BATCH_SIZE = 96


async def ingest_data(file_path: str) -> None:
    """
    Load a PDF, split it into chunks, embed them with Pinecone's
    llama-text-embed-v2 model, and store the vectors in Pinecone.
    """
    # 1. Load PDF
    loader = PyPDFLoader(file_path)
    docs = loader.load()

    # 2. Split into chunks
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = splitter.split_documents(docs)

    # ── DEBUG: save raw extracted text to the python-server folder ──────────
    server_dir = os.path.dirname(os.path.abspath(__file__))
    debug_output_path = os.path.join(server_dir, "extracted_text.txt")
    with open(debug_output_path, "w", encoding="utf-8") as f:
        for i, chunk in enumerate(chunks):
            f.write(f"{'='*60}\n")
            f.write(f"CHUNK {i + 1} (page: {chunk.metadata.get('page', '?')})\n")
            f.write(f"{'='*60}\n")
            f.write(chunk.page_content)
            f.write("\n\n")
    print(f"[Ingest] DEBUG: extracted text saved to → {debug_output_path}")
    # ─────────────────────────────────────────────────────────────────────────

    # 3. Build embeddings — MUST match the model used at query time
    embeddings = PineconeEmbeddings(
        model="llama-text-embed-v2",
        pinecone_api_key=os.environ["PINECONE_API_KEY"],
    )

    # 4. Get the vector store backed by the existing index
    store = PineconeVectorStore(
        index_name=os.environ["PINECONE_INDEX"],
        embedding=embeddings,
        pinecone_api_key=os.environ["PINECONE_API_KEY"],
    )

    # 5. Add documents in batches
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        await store.aadd_documents(batch)

    print("[Ingest] Ingestion Complete!")
