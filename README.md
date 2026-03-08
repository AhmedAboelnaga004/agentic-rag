# 🤖 Agentic Personal Assistant

A full-stack AI assistant that lets you **upload PDF documents** (including handwritten and scanned ones) and **chat with them** using natural language. Powered by Google Gemini 2.5 Flash, Pinecone vector search, LangChain, and a React frontend.

---

## ✨ Features

- 📄 **Smart PDF ingestion** — automatically detects whether a PDF has a real text layer or is image/handwriting-based
- 🧠 **Gemini Vision OCR** — for scanned or handwritten PDFs (e.g. math notes), uses Gemini 2.5 Flash Vision to transcribe each page into clean markdown, including full LaTeX for mathematical expressions
- 🔍 **Semantic search** — chunks are embedded with Pinecone's `llama-text-embed-v2` and stored in a vector database for similarity search
- 💬 **Agentic chat** — a ReAct agent autonomously decides when to search the knowledge base to answer your question
- 🧵 **Per-session memory** — conversation history is maintained per session
- 🔭 **LangSmith tracing** — every LLM call, tool call, token count, and cost is traced end-to-end

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                React Frontend (Vite)                     │
│                   localhost:5173                         │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP
┌──────────────────────▼──────────────────────────────────┐
│              FastAPI Python Server                       │
│                  localhost:8000                          │
│                                                         │
│   POST /api/ingest            POST /api/chat            │
│         │                           │                   │
│    ingest.py                    agent.py                │
│   ┌──────┴──────────┐      ┌────────┴──────────┐        │
│   │ Text PDF?        │      │  ReAct Agent Loop  │        │
│   │  → PyPDFLoader   │      │  Gemini 2.5 Flash  │        │
│   │ Scanned/Handwrit?│      │        │           │        │
│   │  → Gemini Vision │      │  search_knowledge  │        │
│   └─────────────────┘      │  _base (tool)       │        │
│          │                 └────────┬───────────┘        │
│          ▼                          ▼                    │
│     Pinecone Vector DB  ◄───────────┘                   │
└─────────────────────────────────────────────────────────┘
```

---

## 📋 Prerequisites

Make sure you have the following installed:

| Tool | Version | Download |
|------|---------|----------|
| **Node.js** | v18+ | https://nodejs.org |
| **Python** | 3.10+ | https://python.org |
| **npm** | v9+ | Comes with Node.js |

You also need accounts and API keys for:

| Service | Purpose | Get Key |
|---------|---------|---------|
| **Google AI Studio** | Gemini LLM + Vision | https://aistudio.google.com/apikey |
| **Pinecone** | Vector database | https://app.pinecone.io |
| **LangSmith** *(optional)* | Tracing & observability | https://smith.langchain.com |

---

## ⚙️ Setup

### 1. Clone the repository

```bash
git clone https://github.com/AhmedAboelnaga004/agentic-rag.git
cd agentic-rag
```

### 2. Create your Pinecone index

In your [Pinecone console](https://app.pinecone.io):
1. Create a new **Serverless** index
2. Set **Dimensions** to `1024` (required by `llama-text-embed-v2`)
3. Set **Metric** to `cosine`
4. Note down your index name for the `.env` file

### 3. Configure environment variables

Create a file called `.env` inside the `python-server/` folder:

```bash
# python-server/.env

# Google Gemini (LLM + Vision)
GOOGLE_API_KEY=your_google_api_key_here

# Pinecone Vector DB
PINECONE_API_KEY=your_pinecone_api_key_here
PINECONE_INDEX=your_pinecone_index_name_here

# LangSmith — optional but recommended for observability
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=your_langsmith_api_key_here
LANGSMITH_PROJECT=agentic-personal-assistant
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

Go back to the **project root** and run:

```bash
cd ..
npm install
npm --prefix client install --legacy-peer-deps
```

---

## 🚀 Running the App

From the **project root**, start both the backend and frontend together:

```bash
npm run dev
```

This launches:
- 🐍 **Python / FastAPI server** → `http://localhost:8000`
- ⚛️  **React / Vite client** → `http://localhost:5173`

Open your browser at **http://localhost:5173** and start chatting.

### Run them separately

```bash
# Backend only
npm run dev:server

# Frontend only
npm run dev:client
```

---

## 📁 Project Structure

```
agentic-rag/
├── package.json                  # Root scripts (dev, install:all)
│
├── client/                       # React + Vite frontend
│   ├── src/
│   │   ├── App.jsx               # Chat UI + PDF upload
│   │   ├── App.css               # Styling
│   │   └── main.jsx              # React entry point
│   ├── index.html
│   └── package.json
│
└── python-server/                # FastAPI backend
    ├── main.py                   # API routes — /api/chat and /api/ingest
    ├── agent.py                  # ReAct agent loop with Gemini + tool calling
    ├── tools.py                  # search_knowledge_base — Pinecone similarity search
    ├── ingest.py                 # PDF pipeline — text detection + Gemini Vision OCR
    ├── requirements.txt          # Python dependencies
    └── .env                      # Your API keys (never commit this!)
```

---

## 🔄 How It Works

### Uploading a PDF

1. You pick a PDF file in the UI and click upload
2. `ingest.py` opens it with **PyMuPDF** and measures the average characters per page
3. **Text-based PDF** → content is extracted directly with `PyPDFLoader`
4. **Scanned or handwritten PDF** → each page is rendered to a PNG image and sent to **Gemini 2.5 Flash Vision**, which transcribes it to clean markdown (LaTeX is preserved for math)
5. Text is split into 1 000-character chunks with 200-character overlap
6. Chunks are embedded with `llama-text-embed-v2` and uploaded to **Pinecone**

### Chatting

1. You type a message in the UI
2. The **ReAct agent** receives it along with the full session history
3. The agent calls `search_knowledge_base` when it needs information from the uploaded PDF
4. The tool runs a semantic similarity search on Pinecone and returns the top 10 most relevant chunks
5. Gemini reads the retrieved context and writes the final answer
6. The answer is sent back to the UI and saved to memory for future turns

---

## 🔭 Observability with LangSmith

When `LANGSMITH_TRACING=true` is set, every run is fully visible at https://smith.langchain.com:

| What is traced | What you see |
|---|---|
| Agent chat runs | Full message list, tool calls, final answer |
| `search_knowledge_base` tool | Query sent, chunks retrieved |
| Gemini Vision transcription | Per-page: input image → output text, **token count, cost, latency** |
| Pinecone retrieval | Query, similarity scores, results |

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, Vite 7, react-markdown |
| Backend | FastAPI, Uvicorn, Python 3.10+ |
| LLM | Google Gemini 2.5 Flash |
| Vision / OCR | Google Gemini 2.5 Flash (multimodal) |
| Embeddings | Pinecone `llama-text-embed-v2` (1024-dim) |
| Vector DB | Pinecone Serverless |
| AI Framework | LangChain, LangChain-Google-GenAI |
| Observability | LangSmith |
| PDF parsing | PyMuPDF (`fitz`), pypdf |

---

## 🐛 Troubleshooting

| Problem | Fix |
|---------|-----|
| `Import "fastapi" could not be resolved` in VS Code | Select the venv interpreter: **Ctrl+Shift+P** → *Python: Select Interpreter* → choose `python-server/venv/Scripts/python.exe` |
| `exited with code 1` after stopping the server | Normal — this just means you pressed Ctrl+C to stop it |
| Empty `extracted_text.txt` after upload | Your PDF is likely scanned/image-based. Check the server console — it should say `⚠ Image-based PDF detected` and start Gemini Vision transcription |
| Pinecone dimension mismatch error | Make sure your Pinecone index is created with **1024 dimensions** (required by `llama-text-embed-v2`) |
| `GOOGLE_API_KEY` not found | Make sure your `.env` file is inside `python-server/`, not the project root |

---

## 📄 License

MIT
