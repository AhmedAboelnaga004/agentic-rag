from db.repositories.documents import doc_exists


async def is_duplicate_document(course_id: str, file_hash: str) -> bool:
    return await doc_exists(course_id, file_hash)
