import os
import re
import uuid
import asyncio
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter
from langchain_pinecone import PineconeVectorStore, PineconeEmbeddings
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from llama_cloud import AsyncLlamaCloud
from llama_cloud.types.parsing_get_response import (
    MarkdownPageMarkdownResultPage,
    MarkdownPageFailedMarkdownPage,
)

# ── Batch / rate-limit config ────────────────────────────────────────────────
# llama-text-embed-v2 hard ceiling = 96 records per embedding batch.
# Pinecone free tier = 250k embedding tokens/min.
# 96 chunks × ~400 tokens = ~38,400 tokens/batch → sleep 12s between batches
# keeps us well under the cap (5 batches/min = ~192k TPM).
BATCH_SIZE = 96
PINECONE_BATCH_DELAY = 12  # seconds between Pinecone upsert batches

# ── Two-stage chunker config ─────────────────────────────────────────────────
CHUNK_SIZE = 1500
CHUNK_OVERLAP = 300
HEADERS_TO_SPLIT = [("#", "Header1"), ("##", "Header2"), ("###", "Header3")]

# ── LlamaParse config ────────────────────────────────────────────────────────
# cost_effective tier: 3 credits/page — balanced quality at low credit cost.
# Free tier = 10,000 credits/month → ~3,333 pages/month at this tier.
# NOTE: custom parsing instructions are only supported on the 'agentic' tier.
# cost_effective uses LlamaParse's built-in extraction pipeline.
LLAMAPARSE_TIER = "cost_effective"


# ── Helper: content type detection (same as ingest.py) ───────────────────────

def detect_content_type(text: str) -> str:
    if re.search(r"^>\s*\[(Chart|Figure)\]", text, re.MULTILINE | re.IGNORECASE):
        return "visual"
    if re.search(r"^\|.+\|", text, re.MULTILINE):
        return "table"
    if re.search(r"\$\$|\\\[|\\frac|\\sqrt|\\int|\\sum|\\lim|\\vec|\\matrix", text):
        return "formula"
    if re.search(r"^\s*(define|definition|theorem|proof|lemma|corollary|axiom)\b", text, re.MULTILINE | re.IGNORECASE):
        return "definition"
    if re.search(r"^\s*(example|solution|exercise|problem|worked example)\b", text, re.MULTILINE | re.IGNORECASE):
        return "example"
    return "explanation"


def _has_formula(text: str) -> bool:
    return bool(re.search(r"\$|\\\[|\\frac|\\sqrt|\\int|\\sum|\\lim", text))


def _merge_section_heading(metadata: dict) -> str:
    parts = [
        metadata.get("Header1", ""),
        metadata.get("Header2", ""),
        metadata.get("Header3", ""),
    ]
    return " > ".join(p.strip() for p in parts if p.strip())


def _two_stage_split(docs: list[Document]) -> list[Document]:
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=HEADERS_TO_SPLIT,
        strip_headers=False,
    )
    char_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " "],
    )

    stage1: list[Document] = []
    for doc in docs:
        split_docs = header_splitter.split_text(doc.page_content)
        for sd in split_docs:
            sd.metadata["page"] = doc.metadata.get("page", 0)
            sd.metadata["method"] = doc.metadata.get("method", "llamaparse")
            stage1.append(sd)

    stage2: list[Document] = []
    for doc in stage1:
        if len(doc.page_content) > CHUNK_SIZE:
            sub_chunks = char_splitter.split_documents([doc])
            stage2.extend(sub_chunks)
        else:
            stage2.append(doc)

    return stage2


# ── LlamaParse transcription ──────────────────────────────────────────────────

async def _transcribe_pages_with_llamaparse(pdf_path: str) -> list[Document]:
    """
    Upload the PDF to LlamaParse (cost_effective tier) and retrieve per-page
    markdown. Uses the SDK's built-in parse() method which handles job
    submission + polling automatically.

    Returns a list[Document] — one per page — with the same shape as
    _transcribe_pages_with_gemini() in ingest.py so all downstream steps
    (chunking, metadata injection, Pinecone upload) work without changes.

    Uses AsyncLlamaCloud from llama-cloud>=1.0.
    LLAMA_CLOUD_API_KEY is read automatically from the environment.
    """
    client = AsyncLlamaCloud()  # reads LLAMA_CLOUD_API_KEY from env

    print(f"[Ingest-LP] Uploading and parsing PDF with LlamaParse ({LLAMAPARSE_TIER} tier)...")
    print(f"[Ingest-LP] File: {pdf_path}")

    # parse() uploads the file and blocks until the cloud job is complete.
    # expand=["markdown"] requests per-page markdown in the response.
    # verbose=True prints progress to the console.
    # NOTE: custom_prompt is only supported on the 'agentic' tier.
    # For 'cost_effective', LlamaParse uses its built-in extraction pipeline.
    with open(pdf_path, "rb") as f:
        result = await client.parsing.parse(
            tier=LLAMAPARSE_TIER,
            version="latest",
            upload_file=f,
            expand=["markdown"],
            verbose=True,
            timeout=600.0,   # 10 minutes max for large PDFs
        )

    # result.markdown.pages is a list of MarkdownPageMarkdownResultPage |
    # MarkdownPageFailedMarkdownPage objects.
    if not result.markdown or not result.markdown.pages:
        raise RuntimeError("LlamaParse returned no markdown pages. Check the parse job result.")

    documents: list[Document] = []
    for page in result.markdown.pages:
        if isinstance(page, MarkdownPageFailedMarkdownPage):
            print(f"[Ingest-LP] ⚠ Page {page.page_number} failed: {page.error} — using empty string")
            page_md = ""
        else:
            page_md = page.markdown or ""

        documents.append(
            Document(
                page_content=page_md,
                metadata={
                    "page": page.page_number,
                    "source": pdf_path,
                    "method": "llamaparse",
                },
            )
        )

    print(f"[Ingest-LP] Retrieved {len(documents)} page(s) from LlamaParse ✓")
    return documents


# ── Pinecone helpers ──────────────────────────────────────────────────────────

def _is_pinecone_rate_limit(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "too_many_requests" in msg or "rate" in msg or "quota" in msg


@retry(
    retry=retry_if_exception(_is_pinecone_rate_limit),
    wait=wait_exponential(multiplier=2, min=10, max=120),
    stop=stop_after_attempt(5),
    reraise=True,
)
async def _upsert_batch(store: PineconeVectorStore, batch: list) -> None:
    await store.aadd_documents(batch)


# ── Main ingest entry point ───────────────────────────────────────────────────

async def ingest_data_llamaparse(
    file_path: str,
    *,
    university_id: str,
    faculty_id: str,
    semester: str,
    course_id: str,
    course_code: str,
    course_name: str,
    namespace: str,
    doc_title: str,
    doc_type: str,
) -> int:
    """
    LlamaParse variant of the ingestion pipeline.
    Replaces the Gemini Vision transcription step with LlamaParse cloud API.
    All downstream steps (two-stage chunking, metadata injection, Pinecone upload)
    are identical to ingest.py.
    Returns the number of chunks uploaded.
    """
    print(f"[Ingest-LP] ── Received PDF: {file_path}")
    print(f"[Ingest-LP]    University: {university_id} | Course: {course_code} — {course_name}")

    # 1. Upload PDF to LlamaParse and retrieve per-page markdown
    print(f"[Ingest-LP] ▶ LlamaParse pipeline ({LLAMAPARSE_TIER} tier)")
    docs = await _transcribe_pages_with_llamaparse(file_path)
    print(f"[Ingest-LP] Retrieved {len(docs)} page(s) from LlamaParse")

    # 2. Two-stage structure-aware split (identical to ingest.py)
    chunks = _two_stage_split(docs)
    print(f"[Ingest-LP] Split into {len(chunks)} chunk(s) (two-stage)")

    # 3. Inject full academic metadata into every chunk (identical to ingest.py)
    document_id = str(uuid.uuid4())

    for idx, chunk in enumerate(chunks):
        section_heading = _merge_section_heading(chunk.metadata)
        content_type = detect_content_type(chunk.page_content)
        formula_flag = _has_formula(chunk.page_content)

        chunk.metadata.update({
            "university_id":   university_id,
            "faculty_id":      faculty_id,
            "semester":        semester,
            "course_id":       course_id,
            "course_code":     course_code,
            "course_name":     course_name,
            "document_id":     document_id,
            "doc_title":       doc_title,
            "doc_type":        doc_type,
            "page":            chunk.metadata.get("page", 0),
            "section_heading": section_heading,
            "content_type":    content_type,
            "has_formula":     formula_flag,
            "chunk_index":     idx,
            "method":          chunk.metadata.get("method", "llamaparse"),
        })

    # ── DEBUG: save extracted text to python-server folder ────────────────────
    server_dir = os.path.dirname(os.path.abspath(__file__))
    debug_output_path = os.path.join(server_dir, "extracted_text_llamaparse.txt")
    with open(debug_output_path, "w", encoding="utf-8") as f:
        f.write("NOTE: Parsed via LlamaParse (cost_effective tier).\n")
        f.write("      Math is in LaTeX format — this is correct and readable by the AI.\n\n")
        for i, chunk in enumerate(chunks):
            m = chunk.metadata
            f.write(f"{'='*60}\n")
            f.write(
                f"CHUNK {i + 1}  |  page: {m.get('page','?')}  |  "
                f"type: {m.get('content_type','?')}  |  "
                f"formula: {m.get('has_formula','?')}  |  "
                f"section: {m.get('section_heading') or '(none)'}\n"
            )
            f.write(f"{'='*60}\n")
            f.write(chunk.page_content)
            f.write("\n\n")
    print(f"[Ingest-LP] DEBUG: full text saved to → {debug_output_path}")
    # ─────────────────────────────────────────────────────────────────────────

    # 4. Build embeddings
    print("[Ingest-LP] Building embeddings...")
    embeddings = PineconeEmbeddings(
        model="llama-text-embed-v2",
        pinecone_api_key=os.environ["PINECONE_API_KEY"],
    )

    # 5. Get the vector store scoped to this university's namespace
    store = PineconeVectorStore(
        index_name=os.environ["PINECONE_INDEX"],
        embedding=embeddings,
        pinecone_api_key=os.environ["PINECONE_API_KEY"],
        namespace=namespace,
    )

    # 6. Upload in batches with retry + throttle between batches
    print(f"[Ingest-LP] Uploading {len(chunks)} chunk(s) to Pinecone "
          f"(namespace={namespace}) in batches of {BATCH_SIZE}...")
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        await _upsert_batch(store, batch)
        print(f"[Ingest-LP]   Uploaded batch {i // BATCH_SIZE + 1} ({len(batch)} chunks)")
        if i + BATCH_SIZE < len(chunks):
            print(f"[Ingest-LP]   ⏳ Throttling {PINECONE_BATCH_DELAY}s (embedding TPM limit)...")
            await asyncio.sleep(PINECONE_BATCH_DELAY)

    print("[Ingest-LP] ✓ Ingestion Complete!")

    return len(chunks)
