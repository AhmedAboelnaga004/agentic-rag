import sqlalchemy as sa

from core.database import SessionLocal


async def load_session_messages(session_id: str) -> list[dict]:
    query = sa.text(
        """
        SELECT role, content
        FROM messages
        WHERE session_id = :session_id
        ORDER BY created_at ASC
        """
    )
    async with SessionLocal() as session:
        result = await session.execute(query, {"session_id": session_id})
        return [{"role": row.role, "content": row.content} for row in result.fetchall()]


async def append_messages(session_id: str, course_id: str, human_content: str, ai_content: str) -> None:
    query = sa.text(
        """
        INSERT INTO messages (session_id, course_id, role, content)
        VALUES (:session_id, :course_id, :role, :content)
        """
    )
    async with SessionLocal() as session:
        await session.execute(
            query,
            [
                {"session_id": session_id, "course_id": course_id, "role": "human", "content": human_content},
                {"session_id": session_id, "course_id": course_id, "role": "ai", "content": ai_content},
            ],
        )
        await session.commit()
