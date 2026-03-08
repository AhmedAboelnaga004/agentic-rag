import os
import base64
import fitz  # pymupdf
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_pinecone import PineconeVectorStore, PineconeEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI
from langsmith import traceable
from langsmith import Client as LangSmithClient

BATCH_SIZE = 96

# Characters per page threshold — below this we treat the page as image-based
TEXT_CHAR_THRESHOLD = 50


def _is_text_based(pdf_path: str) -> bool:
    """
    Open the PDF with PyMuPDF and check whether it has a real text layer.
    Returns True if the average extracted characters per page exceeds the threshold.
    """
    doc = fitz.open(pdf_path)
    total_chars = sum(len(page.get_text()) for page in doc)
    avg_chars = total_chars / max(len(doc), 1)
    doc.close()
    print(f"[Ingest] Text detection → {total_chars} total chars across {len(fitz.open(pdf_path))} page(s), avg {avg_chars:.1f} chars/page")
    return avg_chars >= TEXT_CHAR_THRESHOLD


def _render_page_as_base64(pdf_path: str, page_index: int, dpi: int = 150) -> str:
    """
    Render a single PDF page to a PNG image and return it as a base64 string.
    """
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    mat = fitz.Matrix(dpi / 72, dpi / 72)  # scale factor from 72 dpi baseline
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    img_bytes = pix.tobytes("png")
    doc.close()
    return base64.b64encode(img_bytes).decode("utf-8")


def _transcribe_single_page(llm: ChatGoogleGenerativeAI, img_b64: str, page_index: int) -> str:
    """
    Send a single rendered page image to Gemini 2.5 Flash for transcription.
    Uses langchain_google_genai so LangSmith automatically captures
    token counts (input/output) and cost for every page call.
    """
    message = HumanMessage(
        content=[
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{img_b64}"},
            },
            {
                "type": "text",
                "text": (
                    "Transcribe ALL text visible in this page into clean markdown. "
                    "Preserve headings, lists, tables, and paragraph structure. "
                    "Output only the transcribed content, no commentary."
                ),
            },
        ]
    )
    response = llm.invoke([message])
    return response.content or ""


@traceable(name="gemini-vision-ingest", run_type="chain", tags=["vision", "ingest"])
def _transcribe_pages_with_gemini(pdf_path: str) -> list[Document]:
    """
    For each page in an image-based PDF, render it to PNG, send it to
    Gemini 2.5 Flash via the LangChain wrapper, and collect transcriptions.
    Using ChatGoogleGenerativeAI means LangSmith automatically records
    input tokens, output tokens, and cost for every single page call.
    """
    # One LLM instance shared across all pages — temperature=0 for deterministic transcription
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=os.environ["GOOGLE_API_KEY"],
        temperature=0,
    )

    doc_fitz = fitz.open(pdf_path)
    total_pages = len(doc_fitz)
    doc_fitz.close()

    print(f"[Ingest] Starting Gemini vision transcription for {total_pages} page(s)...")
    documents: list[Document] = []

    for page_index in range(total_pages):
        print(f"[Ingest]   Transcribing page {page_index + 1}/{total_pages} with Gemini vision...")
        img_b64 = _render_page_as_base64(pdf_path, page_index)

        transcribed_text = _transcribe_single_page(
            llm=llm,
            img_b64=img_b64,
            page_index=page_index,
        )
        print(f"[Ingest]   Page {page_index + 1} → {len(transcribed_text)} chars transcribed")
        documents.append(
            Document(
                page_content=transcribed_text,
                metadata={"page": page_index, "source": pdf_path, "method": "gemini-vision"},
            )
        )

    return documents


async def ingest_data(file_path: str) -> None:
    """
    Load a PDF, auto-detect whether it is text-based or image-based,
    extract/transcribe content accordingly, split into chunks,
    embed with Pinecone's llama-text-embed-v2, and store the vectors.
    """
    print(f"[Ingest] ── Received PDF: {file_path}")

    # 1. Detect PDF type and load documents
    if _is_text_based(file_path):
        print("[Ingest] ✓ Text-based PDF detected → using PyPDFLoader")
        loader = PyPDFLoader(file_path)
        docs = loader.load()
        print(f"[Ingest] Loaded {len(docs)} page(s) via PyPDFLoader")
    else:
        print("[Ingest] ⚠ Image-based / scanned PDF detected → using Gemini vision transcription")
        docs = _transcribe_pages_with_gemini(file_path)
        print(f"[Ingest] Transcribed {len(docs)} page(s) via Gemini vision")

    # 2. Split into chunks
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = splitter.split_documents(docs)
    print(f"[Ingest] Split into {len(chunks)} chunk(s)")

    # ── DEBUG: save extracted/transcribed text to python-server folder ───────
    server_dir = os.path.dirname(os.path.abspath(__file__))
    debug_output_path = os.path.join(server_dir, "extracted_text.txt")
    with open(debug_output_path, "w", encoding="utf-8") as f:
        f.write("NOTE: Math is in LaTeX format — this is correct and readable by the AI.\n")
        f.write("      $ = math delimiter  |  \\frac = fraction  |  \\sqrt = square root  etc.\n\n")
        for i, chunk in enumerate(chunks):
            f.write(f"{'='*60}\n")
            f.write(f"CHUNK {i + 1} (page: {chunk.metadata.get('page', '?')}, method: {chunk.metadata.get('method', 'pypdf')})\n")
            f.write(f"{'='*60}\n")
            f.write(chunk.page_content)
            f.write("\n\n")
    print(f"[Ingest] DEBUG: full text saved to → {debug_output_path}")
    # ─────────────────────────────────────────────────────────────────────────

    # 3. Build embeddings — MUST match the model used at query time
    print("[Ingest] Building embeddings...")
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

    # 5. Upload documents in batches
    print(f"[Ingest] Uploading {len(chunks)} chunk(s) to Pinecone in batches of {BATCH_SIZE}...")
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        await store.aadd_documents(batch)
        print(f"[Ingest]   Uploaded batch {i // BATCH_SIZE + 1} ({len(batch)} chunks)")

    print("[Ingest] ✓ Ingestion Complete!")

    # Flush all pending LangSmith traces so they are marked complete
    # before this function returns — prevents the "spinning" status in LangSmith UI
    try:
        LangSmithClient().flush()
        print("[Ingest] LangSmith traces flushed ✓")
    except Exception:
        pass  # LangSmith is optional — never block ingestion if it fails
