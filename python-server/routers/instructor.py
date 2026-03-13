from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from core.dependencies import get_optional_token_payload
from db.repositories.subjects import get_course_context_for_staff
from db.repositories.usage import upsert_usage_log
from models.document import DocumentStatus
from services.ingestion.pipeline import ingest_document


router = APIRouter(prefix="/instructor", tags=["instructor"])
compat_router = APIRouter(prefix="/api", tags=["instructor-compat"])



def _estimate_ingest_cost_usd(technique: str, chunk_count: int) -> float:
    if technique == "llamaparse":
        return max(0.01, chunk_count * 0.003)
    return max(0.005, chunk_count * 0.001)


async def _ingest_impl(
    *,
    file: UploadFile,
    user_id: str,
    university_id: str,
    faculty_id: str,
    semester: str,
    course_id: str,
    course_code: str,
    course_name: str,
    doc_title: str,
    doc_type: str,
    technique: str,
) -> DocumentStatus:
    is_pdf = file.content_type == "application/pdf" or (file.filename or "").lower().endswith(".pdf")
    if not is_pdf:
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    context = await get_course_context_for_staff(staff_user_id=user_id, course_id=course_id)
    if not context:
        raise HTTPException(status_code=403, detail="Access denied: only active professor/admin users can upload to this course.")

    if context["university_id"] != university_id or context["faculty_id"] != faculty_id:
        raise HTTPException(status_code=400, detail="University/faculty mismatch for selected course")
    if context["semester_id"] != semester:
        raise HTTPException(status_code=400, detail="Semester mismatch for selected course")

    file_bytes = await file.read()

    try:
        document_id, chunk_count = await ingest_document(
            file_bytes=file_bytes,
            filename=file.filename or "unknown.pdf",
            technique=technique,
            user_id=user_id,
            university_id=context["university_id"],
            faculty_id=context["faculty_id"],
            semester=context["semester_id"],
            course_id=context["course_id"],
            course_code=context["course_code"],
            course_name=context["course_name"],
            namespace=context["pinecone_namespace"],
            doc_title=doc_title,
            doc_type=doc_type,
        )
        await upsert_usage_log(
            university_id=context["university_id"],
            ingest_requests_inc=1,
            estimated_cost_usd_inc=_estimate_ingest_cost_usd(technique, chunk_count),
        )
        return DocumentStatus(ok=True, chunks=chunk_count, documentId=document_id)
    except FileExistsError as exc:
        await upsert_usage_log(university_id=context["university_id"], ingest_requests_inc=1, failed_requests_inc=1)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        await upsert_usage_log(university_id=context["university_id"], ingest_requests_inc=1, failed_requests_inc=1)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/ingest", response_model=DocumentStatus)
async def ingest(
    file: UploadFile = File(...),
    user_id: str = Form(...),
    university_id: str = Form(...),
    faculty_id: str = Form(...),
    semester: str = Form(...),
    course_id: str = Form(...),
    course_code: str = Form(...),
    course_name: str = Form(...),
    doc_title: str = Form(...),
    doc_type: str = Form(...),
    technique: str = Form("gemini"),
    _: dict | None = Depends(get_optional_token_payload),
):
    return await _ingest_impl(
        file=file,
        user_id=user_id,
        university_id=university_id,
        faculty_id=faculty_id,
        semester=semester,
        course_id=course_id,
        course_code=course_code,
        course_name=course_name,
        doc_title=doc_title,
        doc_type=doc_type,
        technique=technique,
    )


@compat_router.post("/ingest", response_model=DocumentStatus, include_in_schema=False)
async def ingest_compat(
    file: UploadFile = File(...),
    user_id: str = Form(...),
    university_id: str = Form(...),
    faculty_id: str = Form(...),
    semester: str = Form(...),
    course_id: str = Form(...),
    course_code: str = Form(...),
    course_name: str = Form(...),
    doc_title: str = Form(...),
    doc_type: str = Form(...),
    technique: str = Form("gemini"),
):
    return await _ingest_impl(
        file=file,
        user_id=user_id,
        university_id=university_id,
        faculty_id=faculty_id,
        semester=semester,
        course_id=course_id,
        course_code=course_code,
        course_name=course_name,
        doc_title=doc_title,
        doc_type=doc_type,
        technique=technique,
    )
