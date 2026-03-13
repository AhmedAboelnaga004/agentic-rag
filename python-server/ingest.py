import os
import re
import uuid
import base64
import time
import fitz  # pymupdf
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage
from langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter
from langchain_pinecone import PineconeVectorStore, PineconeEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI
from langsmith import traceable
from langsmith import Client as LangSmithClient
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

BATCH_SIZE = 96

# ── Rate-limit config ────────────────────────────────────────────────────────
# Free-tier Gemini 2.5 Flash = 4 RPM assumed → 1 request per 15 s minimum.
# The proactive sleep keeps us under the limit; tenacity handles any 429 that
# still slips through (e.g. burst / TPM cap).
GEMINI_RPM = 4
GEMINI_RPM_DELAY = 60 / GEMINI_RPM  # = 15.0 seconds between pages

# ── Two-stage chunker config ─────────────────────────────────────────────────
CHUNK_SIZE = 1500
CHUNK_OVERLAP = 300
HEADERS_TO_SPLIT = [("#", "Header1"), ("##", "Header2"), ("###", "Header3")]


def _is_gemini_rate_limit(exc: Exception) -> bool:
    """Return True for any exception that looks like a Gemini quota / rate-limit error."""
    msg = str(exc).lower()
    return "429" in msg or "resource has been exhausted" in msg or "quota" in msg


def detect_content_type(text: str) -> str:
    """
    Heuristically classify the primary content type of a chunk.
    Checks are ordered from most specific to most general.
    """
    # Visual: Gemini-prefixed chart or figure descriptions
    if re.search(r"^>\s*\[(Chart|Figure)\]", text, re.MULTILINE | re.IGNORECASE):
        return "visual"
    # Table: GFM table rows (| col | col |)
    if re.search(r"^\|.+\|", text, re.MULTILINE):
        return "table"
    # Formula: LaTeX delimiters or display math
    if re.search(r"\$\$|\\\[|\\frac|\\sqrt|\\int|\\sum|\\lim|\\vec|\\matrix", text):
        return "formula"
    # Definition: definition-style keywords at line start
    if re.search(r"^\s*(define|definition|theorem|proof|lemma|corollary|axiom)\b", text, re.MULTILINE | re.IGNORECASE):
        return "definition"
    # Example / solution blocks
    if re.search(r"^\s*(example|solution|exercise|problem|worked example)\b", text, re.MULTILINE | re.IGNORECASE):
        return "example"
    return "explanation"


def _has_formula(text: str) -> bool:
    """Return True if the chunk contains any LaTeX math expression."""
    return bool(re.search(r"\$|\\\[|\\frac|\\sqrt|\\int|\\sum|\\lim", text))


def _merge_section_heading(metadata: dict) -> str:
    """
    Merge MarkdownHeaderTextSplitter header fields into a single
    human-readable breadcrumb string, e.g. 'Lecture 3 > Examples > Step 2'.
    """
    parts = [
        metadata.get("Header1", ""),
        metadata.get("Header2", ""),
        metadata.get("Header3", ""),
    ]
    return " > ".join(p.strip() for p in parts if p.strip())


def _two_stage_split(docs: list[Document]) -> list[Document]:
    """
    Stage 1 — split on Markdown headers so each chunk stays within one section.
    Stage 2 — apply RecursiveCharacterTextSplitter only to chunks still >CHUNK_SIZE
              so short sections are never broken unnecessarily.
    Page number is propagated from the source document to all child chunks.
    """
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=HEADERS_TO_SPLIT,
        strip_headers=False,  # keep headers inside the chunk text for context
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
            # Carry page and method from parent into every header-split chunk
            sd.metadata["page"] = doc.metadata.get("page", 0)
            sd.metadata["method"] = doc.metadata.get("method", "gemini-vision")
            stage1.append(sd)

    stage2: list[Document] = []
    for doc in stage1:
        if len(doc.page_content) > CHUNK_SIZE:
            sub_chunks = char_splitter.split_documents([doc])
            stage2.extend(sub_chunks)
        else:
            stage2.append(doc)

    return stage2



def _render_page_as_base64(pdf_path: str, page_index: int, dpi: int = 175) -> str:
    """
    Render a single PDF page to a PNG image at 175 DPI and return it as a base64 string.
    175 DPI is the sweet spot: sharp enough for small-font text and math symbols
    without the large token overhead of 200–300 DPI renders.
    """
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    mat = fitz.Matrix(dpi / 72, dpi / 72)  # scale factor from 72 dpi baseline
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    img_bytes = pix.tobytes("png")
    doc.close()
    return base64.b64encode(img_bytes).decode("utf-8")

#TODO: low retry time 
@retry(
    retry=retry_if_exception(_is_gemini_rate_limit),
    wait=wait_exponential(multiplier=1, min=15, max=90),
    stop=stop_after_attempt(6),
    reraise=True,
)
def _transcribe_single_page(llm: ChatGoogleGenerativeAI, img_b64: str, page_index: int) -> str:
    """
    Send a single rendered page image to Gemini 2.5 Flash for transcription.
    Uses langchain_google_genai so LangSmith automatically captures
    token counts (input/output) and cost for every page call.
    If a 429 rate-limit error is returned, tenacity retries with exponential
    backoff: 15 s → 30 s → 60 s → 90 s … up to 6 attempts total.
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
                    "You are a precise document transcription engine. "
                    "Transcribe ALL content visible on this page into clean Markdown. "
                    "Follow these rules strictly:\n\n"
                    "- **Regular text**: preserve paragraphs, headings (use #/##/###), "
                    "bullet lists, and numbered lists.\n"
                    "- **Tables**: reproduce as GitHub-Flavored Markdown tables (| col | col |).\n"
                    "- **Math / equations**: render ALL mathematical expressions in LaTeX — "
                    "inline as $...$ and display/block as $$...$$. "
                    "Do NOT use Unicode math symbols (e.g. use $\\sqrt{x}$ not √x).\n"
                    "- **Charts / graphs**: describe the chart type, axis labels, data series, "
                    "and key values in a compact paragraph prefixed with '> [Chart]:'.\n"
                    "- **Diagrams / figures**: describe the structure, components, and all "
                    "label text in a paragraph prefixed with '> [Figure]:'.\n"
                    "- **Handwriting**: transcribe as plain text; mark uncertain words with [?].\n"
                    "- **Code blocks**: wrap in triple-backtick fences with the detected language.\n"
                    "- Do NOT add commentary, summaries, or any content not present on the page.\n"
                    "- Do NOT wrap the entire output in a code block — output raw Markdown only."
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
        # Proactive throttle — wait before every call except the first so we
        # never exceed 4 RPM and avoid hitting the quota in the first place.
        if page_index > 0:
            print(f"[Ingest]   ⏳ Throttling {GEMINI_RPM_DELAY:.0f}s (4 RPM free-tier limit)...")
            time.sleep(GEMINI_RPM_DELAY)

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


async def ingest_data(
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
    Transcribe a PDF with Gemini Vision, split into structure-aware chunks,
    inject full academic metadata into every chunk, and upload to Pinecone
    under the university's dedicated namespace.
    Returns the number of chunks uploaded.
    """
    print(f"[Ingest] ── Received PDF: {file_path}")
    print(f"[Ingest]    University: {university_id} | Course: {course_code} — {course_name}")

    # 1. Render every page as an image and transcribe with Gemini 2.5 Flash Vision.
    print("[Ingest] ▶ Vision pipeline → rendering all pages at 175 DPI → Gemini 2.5 Flash")
    docs = _transcribe_pages_with_gemini(file_path)
    print(f"[Ingest] Transcribed {len(docs)} page(s) via Gemini vision")

    # 2. Two-stage structure-aware split
    #    Stage 1: split on #/##/### headers (respects document structure)
    #    Stage 2: further split only chunks that exceed CHUNK_SIZE characters
    chunks = _two_stage_split(docs)
    print(f"[Ingest] Split into {len(chunks)} chunk(s) (two-stage)")

    # 3. Inject full academic metadata into every chunk
    document_id = str(uuid.uuid4())

    for idx, chunk in enumerate(chunks):
        section_heading = _merge_section_heading(chunk.metadata)
        content_type = detect_content_type(chunk.page_content)
        formula_flag = _has_formula(chunk.page_content)

        chunk.metadata.update({
            # ── Academic context ─────────────────────────────────────────
            "university_id":   university_id,
            "faculty_id":      faculty_id,
            "semester":        semester,
            "course_id":       course_id,
            "course_code":     course_code,
            "course_name":     course_name,
            # ── Document identity ────────────────────────────────────────
            "document_id":     document_id,
            "doc_title":       doc_title,
            "doc_type":        doc_type,
            # ── Chunk position & content classification ──────────────────
            "page":            chunk.metadata.get("page", 0),
            "section_heading": section_heading,
            "content_type":    content_type,
            "has_formula":     formula_flag,
            "chunk_index":     idx,
            "method":          chunk.metadata.get("method", "gemini-vision"),
        })

    # ── DEBUG: save extracted/transcribed text to python-server folder ───────
    server_dir = os.path.dirname(os.path.abspath(__file__))
    debug_output_path = os.path.join(server_dir, "extracted_text.txt")
    with open(debug_output_path, "w", encoding="utf-8") as f:
        f.write("NOTE: Math is in LaTeX format — this is correct and readable by the AI.\n")
        f.write("      $ = math delimiter  |  \\frac = fraction  |  \\sqrt = square root  etc.\n\n")
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
    print(f"[Ingest] DEBUG: full text saved to → {debug_output_path}")
    # ─────────────────────────────────────────────────────────────────────────

    # 4. Build embeddings — MUST match the model used at query time
    print("[Ingest] Building embeddings...")
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

    # 6. Upload documents in batches
    print(f"[Ingest] Uploading {len(chunks)} chunk(s) to Pinecone "
          f"(namespace={namespace}) in batches of {BATCH_SIZE}...")
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        await store.aadd_documents(batch)
        print(f"[Ingest]   Uploaded batch {i // BATCH_SIZE + 1} ({len(batch)} chunks)")

    print("[Ingest] ✓ Ingestion Complete!")

    return len(chunks)

    # Flush all pending LangSmith traces so they are marked complete
    try:
        LangSmithClient().flush()
        print("[Ingest] LangSmith traces flushed ✓")
    except Exception:
        pass  # LangSmith is optional — never block ingestion if it fails
