# Agentic Study Assistant

A full-stack AI assistant for university students. Upload your course PDFs and chat with them using natural language. Built with Google Gemini 2.5 Flash, Pinecone vector search, LangChain, and a React frontend.

Supports **multi-tenant, multi-course** architecture -- each university gets its own Pinecone namespace, each course is isolated by metadata filters, and the agent is locked to the active course so it can never bleed context across subjects.

---

## Features

- **Multi-tenant by design** -- namespace per university, course-locked sessions, agent physically cannot return data from other courses
- **Two ingestion pipelines** -- choose per upload:
  - **Gemini Vision** (Recommended for math/handwriting) -- renders each page to PNG, sends to Gemini 2.5 Flash Vision; full LaTeX math preserved
  - **LlamaParse** (Fast) -- uploads PDF to LlamaParse cloud API, returns markdown; no per-page throttle; best for clean printed documents
- **Structure-aware chunking** -- two-stage split: first on `#`/`##`/`###` Markdown headers, then `RecursiveCharacterTextSplitter` only on chunks that exceed the size limit
- **Rich 13-field metadata** per chunk -- `university_id`, `faculty_id`, `semester`, `course_id`, `course_code`, `course_name`, `document_id`, `doc_title`, `doc_type`, `page`, `section_heading`, `content_type`, `has_formula`
- **Two search tools** -- plain semantic search and filtered search (by section heading, content type, formula presence)
- **Agentic ReAct loop** -- Gemini decides when to search, which tool to use, and how many times
- **Per-session memory** -- conversation history maintained per session ID
- **KaTeX math rendering** -- AI responses render `\$...\$` and `\$\$...\$\$` LaTeX correctly in the browser
- **LangSmith tracing** -- every LLM call, tool call, token count, and cost traced end-to-end

---

## Architecture

```
+------------------------------------------------------------+
|                   React Frontend (Vite)                    |
|   Course context setup -> locked session -> chat + upload  |
|                       localhost:5173                       |
+---------------------------+--------------------------------+
                            | HTTP
+---------------------------v--------------------------------+
|               FastAPI Python Server  :8000                 |
|                                                            |
|   POST /api/ingest               POST /api/chat            |
|   technique=gemini|llamaparse    university_id             |
|          |                       course_id                 |
|     +----+------+                course_name               |
|     |           |                     |                    |
|  ingest.py  ingest_              agent.py                  |
|  (Gemini    llamaparse.py        ReAct loop                 |
|   Vision)   (LlamaParse)         Gemini 2.5 Flash           |
|     |           |                     |                    |
|     +----+------+             tools.py (search)            |
|          |                           |                     |
|   Two-stage chunker                  |                     |
|   13-field metadata                  |                     |
|          |                           |                     |
|          v                           v                     |
|      Pinecone <------- namespace: uni_{university_id}      |
|   llama-text-embed-v2    filter: course_id == X            |
+------------------------------------------------------------+
```

---

## Prerequisites

| Tool | Version | Download |
|------|---------|----------|
| **Node.js** | v18+ | https://nodejs.org |
| **Python** | 3.10+ | https://python.org |
| **npm** | v9+ | Comes with Node.js |

---

## API Keys You Need

You need accounts and API keys for **4 services**.

### 1. Google AI Studio -- `GOOGLE_API_KEY`

**What it does:** Powers the AI brain. The ReAct agent uses Gemini 2.5 Flash for reasoning and answering questions. If you choose the **Gemini Vision** ingestion pipeline, it also transcribes PDF pages to markdown by looking at rendered images of each page, preserving full LaTeX math.

**Free tier:** 15 requests/minute, 1 million tokens/day.

**Where to get it:** https://aistudio.google.com/apikey

---

### 2. Pinecone -- `PINECONE_API_KEY` + `PINECONE_INDEX`

**What it does:** The vector database where your document chunks are stored after ingestion. Every time you ask a question, the agent searches Pinecone to find the most semantically relevant passages. Searches are always filtered by `course_id` so students can only retrieve their own course material.

**Setup steps:**
1. Create a free account at https://app.pinecone.io
2. Create a new **Serverless** index:
   - **Dimensions:** `1024` (required by `llama-text-embed-v2`)
   - **Metric:** `cosine`
3. Copy your **API key** and **index name**

**Free tier:** 100k vectors, 2 GB storage.

---

### 3. LlamaCloud -- `LLAMA_CLOUD_API_KEY`

**What it does:** Powers the **LlamaParse** ingestion option (the fast option in the upload form). Your PDF is uploaded to LlamaParse's cloud which converts it to structured markdown. No GPU needed locally. The SDK handles job submission and polling automatically.

**Free tier:** 10,000 credits/month. The app uses `cost_effective` tier (3 credits/page) -> ~3,333 pages/month free.

**Where to get it:** https://cloud.llamaindex.ai -> sign in -> API Keys

> **Optional:** If you only want to use Gemini Vision, you can leave this blank. The upload form lets you switch between pipelines per upload.

---

### 4. LangSmith -- `LANGSMITH_API_KEY` *(optional)*

**What it does:** Observability dashboard. Every LLM call, tool call, token count, latency, and cost is recorded automatically. Useful for debugging what the agent is doing internally.

**Where to get it:** https://smith.langchain.com -> Settings -> API Keys

**To disable:** Set `LANGSMITH_TRACING=false` in your `.env`.

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/tariqlabs/agentic-personal-assistant.git
cd agentic-personal-assistant
```

### 2. Create your Pinecone index

In your [Pinecone console](https://app.pinecone.io):
1. Create a new **Serverless** index
2. Set **Dimensions** to `1024`
3. Set **Metric** to `cosine`
4. Note down the index name

### 3. Configure environment variables

Copy the example file and fill in your keys:

```bash
cp python-server/.env.example python-server/.env
```

```env
# python-server/.env

# Google Gemini (LLM + Vision ingestion)
# Get from: https://aistudio.google.com/apikey
GOOGLE_API_KEY=your_google_api_key_here

# Pinecone (vector database)
# Get from: https://app.pinecone.io -> API Keys
PINECONE_API_KEY=your_pinecone_api_key_here
# The name you gave your index (must be 1024-dim cosine serverless)
PINECONE_INDEX=your_pinecone_index_name_here

# LlamaParse (fast PDF ingestion pipeline)
# Get from: https://cloud.llamaindex.ai -> API Keys
# Optional -- only needed if you use the LlamaParse option in the upload form
LLAMA_CLOUD_API_KEY=your_llama_cloud_api_key_here

# LangSmith (optional -- tracing & observability)
# Get from: https://smith.langchain.com -> Settings -> API Keys
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=your_langsmith_api_key_here
LANGSMITH_PROJECT=agentic-rag
```

### 4. Set up the Python virtual environment

```bash
cd python-server
python -m venv venv
```

Activate it:

```bash
# Windows (PowerShell)
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

Install all Python dependencies:

```bash
pip install -r requirements.txt
```

### 5. Install Node.js dependencies

From the **project root**:

```bash
npm install
npm --prefix client install
```

---

## Running the App

From the **project root**:

```bash
npm run dev
```

This launches:
- **FastAPI backend** -> `http://localhost:8000`
- **React/Vite frontend** -> `http://localhost:5173`

Open **http://localhost:5173** in your browser.

### Run separately

```bash
# Backend only
npm run dev:server

# Frontend only
npm run dev:client
```

---

## Using the App

### 1. Set up your course context

When you open the app you will see a **Course Context** form. Fill in:

| Field | Example | Purpose |
|-------|---------|---------|
| University ID | `CAIRO_UNI` | Determines Pinecone namespace (`uni_CAIRO_UNI`) |
| Faculty ID | `ENGINEERING` | Stored as metadata on every chunk |
| Semester | `2025-SPRING` | Stored as metadata |
| Course ID | `MATH101` | Filters search -- you only ever see chunks from this course |
| Course Code | `MATH101` | Display label |
| Course Name | `Calculus 1` | Shown in UI and passed to the agent |

Click **Start Session**. The session is locked to this course until you click **Change course**.

### 2. Upload a PDF

In the upload panel:
1. Choose your PDF file
2. Enter a document title
3. Select a document type (Lecture, Textbook, Assignment, etc.)
4. Choose your ingestion technique:
   - **LlamaParse** -- uploads to cloud, returns markdown; faster, good for clean printed PDFs
   - **Gemini Vision** -- renders every page as an image and sends to Gemini; best for scanned notes and heavy math; slower (15s/page on free tier)
5. Click **Upload**

A debug file is saved to `python-server/` (`extracted_text_llamaparse.txt` or `extracted_text.txt`) so you can inspect exactly what the AI extracted.

### 3. Chat

Type a question and press Enter. The agent searches the uploaded documents and answers using retrieved context. Math formulas are rendered with KaTeX.

---

## Project Structure

```
agentic-personal-assistant/
+-- package.json                   # Root scripts (dev, install:all)
|
+-- client/                        # React + Vite frontend
|   +-- src/
|   |   +-- App.jsx                # Course context, upload form, chat UI, KaTeX rendering
|   |   +-- App.css                # Styling
|   |   +-- main.jsx               # React entry point
|   +-- package.json
|
+-- python-server/                 # FastAPI backend
    +-- main.py                    # Routes: /api/chat and /api/ingest (technique routing)
    +-- agent.py                   # ReAct agent -- Gemini 2.5 Flash + tools + session memory
    +-- tools.py                   # search_course + search_course_filtered, namespace-aware
    +-- ingest.py                  # Gemini Vision pipeline: PDF -> PNG -> Gemini -> Pinecone
    +-- ingest_llamaparse.py       # LlamaParse pipeline: PDF -> cloud parse -> Pinecone
    +-- requirements.txt           # Python dependencies
    +-- .env                       # Your API keys -- NEVER commit this!
    +-- .env.example               # Template -- copy to .env and fill in your keys
```

---

## How It Works

### Ingestion -- Gemini Vision (`ingest.py`)

1. Each page is rendered to PNG at 175 DPI with **PyMuPDF**
2. The image is sent to **Gemini 2.5 Flash Vision** with a transcription prompt that enforces LaTeX math (`\$...\$` / `\$\$...\$\$`)
3. A 15-second throttle between pages prevents hitting the 4 RPM free-tier limit; `tenacity` retries on 429s
4. Transcribed markdown -> two-stage chunker -> 13-field metadata -> Pinecone

### Ingestion -- LlamaParse (`ingest_llamaparse.py`)

1. PDF is uploaded to LlamaParse cloud via `AsyncLlamaCloud` (`cost_effective` tier)
2. `parse()` handles job submission and polling automatically
3. Per-page markdown returned as `result.markdown.pages[i].markdown`
4. Same two-stage chunker, metadata injection, and Pinecone upsert (with retry + 12s throttle between batches) as the Gemini pipeline

### Two-stage chunking

- **Stage 1:** `MarkdownHeaderTextSplitter` splits on `#`/`##`/`###` -- keeps each chunk within one section
- **Stage 2:** `RecursiveCharacterTextSplitter` (1500 chars, 300 overlap) only runs on chunks still above the size limit

### Chat

1. Frontend sends `message + university_id + course_id + course_name`
2. `agent.py` builds a dynamic system prompt locking the agent to the active course
3. Tools use `functools.partial` to pre-fill `university_id` and `course_id` -- the LLM never sees these fields and cannot hallucinate them
4. Pinecone search **always** applies `course_id == X` -- physically impossible to retrieve chunks from another course
5. Answer saved to in-memory session history for multi-turn conversation

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, Vite 7, `react-markdown`, `remark-math`, `rehype-katex` |
| Backend | FastAPI, Uvicorn, Python 3.10+ |
| LLM & Vision | Google Gemini 2.5 Flash (`langchain-google-genai`) |
| PDF ingestion A | PyMuPDF + Gemini 2.5 Flash Vision |
| PDF ingestion B | LlamaParse (`llama-cloud>=1.0`, `cost_effective` tier) |
| Embeddings | Pinecone `llama-text-embed-v2` (1024-dim) |
| Vector DB | Pinecone Serverless (`langchain-pinecone`) |
| AI Framework | LangChain, LangChain-Core |
| Retry logic | `tenacity` |
| Observability | LangSmith |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Import "fastapi" could not be resolved` in VS Code | **Ctrl+Shift+P** -> *Python: Select Interpreter* -> pick `python-server/venv/Scripts/python.exe` |
| `GOOGLE_API_KEY not found` | Make sure `.env` is inside `python-server/`, not the project root |
| Pinecone dimension mismatch | Index must be created with **1024 dimensions** and `cosine` metric |
| LlamaParse `401 Unauthorized` | Check `LLAMA_CLOUD_API_KEY` is set correctly in `python-server/.env` |
| Upload slow with Gemini Vision | Expected -- 15s throttle per page on free tier. 10 pages = ~2.5 min. Use LlamaParse for speed. |
| Math shows as raw text | KaTeX rendering issue. Check the browser console for KaTeX errors. |
| `exited with code 1` after stopping | Normal -- happens when you press Ctrl+C |

---

## License

MIT