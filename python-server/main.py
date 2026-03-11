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

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent import run_agent
from ingest import ingest_data
from ingest_llamaparse import ingest_data_llamaparse

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
    # Course context — sent by the frontend on every message.
    # The agent uses these to lock search to the student's course and namespace.
    university_id: str
    course_id: str
    course_name: str


class ChatResponse(BaseModel):
    answer: str


# ── Routes ───────────────────────────────────────────────────────────────────

@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message required")

    try:
        output = await run_agent(
            message=req.message,
            session_id=req.sessionId,
            university_id=req.university_id,
            course_id=req.course_id,
            course_name=req.course_name,
        )
        if not output or not output.strip():
            return ChatResponse(
                answer="I apologize, but I couldn't generate a proper response. Could you please rephrase your question?"
            )
        return ChatResponse(answer=output)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ingest")
async def ingest(
    file: UploadFile = File(...),
    university_id: str = Form(...),
    faculty_id: str = Form(...),
    semester: str = Form(...),
    course_id: str = Form(...),
    course_code: str = Form(...),
    course_name: str = Form(...),
    doc_title: str = Form(...),
    doc_type: str = Form(...),
    technique: str = Form("gemini"),  # "gemini" | "llamaparse"
):
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
        ingest_fn = ingest_data_llamaparse if technique == "llamaparse" else ingest_data
        await ingest_fn(
            tmp.name,
            university_id=university_id,
            faculty_id=faculty_id,
            semester=semester,
            course_id=course_id,
            course_code=course_code,
            course_name=course_name,
            doc_title=doc_title,
            doc_type=doc_type,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        os.unlink(tmp.name)

    return {"ok": True}


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
