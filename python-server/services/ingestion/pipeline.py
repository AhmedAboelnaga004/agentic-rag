from pathlib import Path
import hashlib
import tempfile

from db.repositories import documents as documents_repo
from services.ingestion.parser import resolve_parser


async def ingest_document(
    *,
    file_bytes: bytes,
    filename: str,
    technique: str,
    user_id: str,
    university_id: str,
    faculty_id: str,
    semester: str,
    course_id: str,
    course_code: str,
    course_name: str,
    namespace: str,
    doc_title: str,
    doc_type: str,
) -> tuple[int, int]:
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    if await documents_repo.doc_exists(course_id, file_hash):
        raise FileExistsError("This document is already in this course's knowledge base.")

    document_id = await documents_repo.create_document_record(
        university_id=university_id,
        faculty_id=faculty_id,
        semester_id=semester,
        course_id=course_id,
        course_code=course_code,
        course_name=course_name,
        uploaded_by_user_id=user_id,
        doc_title=doc_title,
        doc_type=doc_type,
        technique=technique,
        file_hash=file_hash,
        original_filename=filename,
    )

    suffix = Path(filename or "upload.pdf").suffix or ".pdf"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(file_bytes)
        tmp.close()

        ingest_fn = resolve_parser(technique)
        chunk_count = await ingest_fn(
            tmp.name,
            university_id=university_id,
            faculty_id=faculty_id,
            semester=semester,
            course_id=course_id,
            course_code=course_code,
            course_name=course_name,
            namespace=namespace,
            doc_title=doc_title,
            doc_type=doc_type,
        )
        await documents_repo.update_document_status(document_id=document_id, status="ready", chunk_count=chunk_count)
        return document_id, chunk_count
    except Exception as exc:
        await documents_repo.update_document_status(document_id=document_id, status="failed", chunk_count=0, error_message=str(exc))
        raise
    finally:
        import os

        if tmp.name and os.path.exists(tmp.name):
            os.unlink(tmp.name)
