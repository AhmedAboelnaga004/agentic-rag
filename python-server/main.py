import os
import sys
import tempfile
import shutil
from pathlib import Path

# Force UTF-8 output on Windows so emoji in log messages don't crash the server
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent import run_agent
from ingest import ingest_data

app = FastAPI(title="Personal Assistant")

# Allow the React dev server (port 5173) and any localhost origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response models ────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    sessionId: str = "default"


class ChatResponse(BaseModel):
    answer: str


# ── Routes ───────────────────────────────────────────────────────────────────

@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message required")

    try:
        output = await run_agent(message=req.message, session_id=req.sessionId)
        if not output or not output.strip():
            return ChatResponse(
                answer="I apologize, but I couldn't generate a proper response. Could you please rephrase your question?"
            )
        return ChatResponse(answer=output)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ingest")
async def ingest(file: UploadFile = File(...)):
    # Validate PDF
    is_pdf = (
        file.content_type == "application/pdf"
        or (file.filename or "").lower().endswith(".pdf")
    )
    if not is_pdf:
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    # Save to a temp file
    suffix = Path(file.filename or "upload").suffix or ".pdf"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        shutil.copyfileobj(file.file, tmp)
        tmp.close()
        await ingest_data(tmp.name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        os.unlink(tmp.name)

    return {"ok": True}


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
