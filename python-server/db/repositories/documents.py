import sqlalchemy as sa

from core.database import SessionLocal


async def doc_exists(course_id: str, file_hash: str) -> bool:
    query = sa.text("SELECT 1 FROM documents WHERE course_id = :course_id AND file_hash = :file_hash LIMIT 1")
    async with SessionLocal() as session:
        result = await session.execute(query, {"course_id": course_id, "file_hash": file_hash})
        return result.fetchone() is not None


async def create_document_record(
    *,
    university_id: str,
    faculty_id: str,
    semester_id: str,
    course_id: str,
    course_code: str,
    course_name: str,
    uploaded_by_user_id: str,
    doc_title: str,
    doc_type: str,
    technique: str,
    file_hash: str,
    original_filename: str,
) -> int:
    query = sa.text(
        """
        INSERT INTO documents
            (university_id, faculty_id, semester_id, course_id, course_code, course_name,
             uploaded_by_user_id, doc_title, doc_type, technique, file_hash,
             original_filename, status, chunk_count)
        VALUES
            (:university_id, :faculty_id, :semester_id, :course_id, :course_code, :course_name,
             :uploaded_by_user_id, :doc_title, :doc_type, :technique, :file_hash,
             :original_filename, 'processing', 0)
        RETURNING id
        """
    )
    async with SessionLocal() as session:
        result = await session.execute(
            query,
            {
                "university_id": university_id,
                "faculty_id": faculty_id,
                "semester_id": semester_id,
                "course_id": course_id,
                "course_code": course_code,
                "course_name": course_name,
                "uploaded_by_user_id": uploaded_by_user_id,
                "doc_title": doc_title,
                "doc_type": doc_type,
                "technique": technique,
                "file_hash": file_hash,
                "original_filename": original_filename,
            },
        )
        await session.commit()
        row = result.fetchone()
        return int(row.id)


async def update_document_status(*, document_id: int, status: str, chunk_count: int = 0, error_message: str | None = None) -> None:
    query = sa.text(
        """
        UPDATE documents
        SET status = :status,
            chunk_count = :chunk_count,
            error_message = :error_message,
            updated_at = NOW()
        WHERE id = :document_id
        """
    )
    async with SessionLocal() as session:
        await session.execute(
            query,
            {
                "status": status,
                "chunk_count": chunk_count,
                "error_message": error_message,
                "document_id": document_id,
            },
        )
        await session.commit()
