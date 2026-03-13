import uuid
import sqlalchemy as sa

from core.database import SessionLocal


async def get_or_create_session(*, student_user_id: str, course_id: str, client_session_id: str | None = None) -> str:
    async with SessionLocal() as session:
        existing = await session.execute(
            sa.text(
                """
                SELECT id FROM sessions
                WHERE student_user_id = :student_user_id AND course_id = :course_id
                LIMIT 1
                """
            ),
            {"student_user_id": student_user_id, "course_id": course_id},
        )
        row = existing.fetchone()
        if row:
            session_id = row.id
            await session.execute(sa.text("UPDATE sessions SET updated_at = NOW() WHERE id = :sid"), {"sid": session_id})
            await session.commit()
            return session_id

        session_id = str(uuid.uuid4())
        await session.execute(
            sa.text(
                """
                INSERT INTO sessions (id, student_user_id, course_id, client_session_id)
                VALUES (:id, :student_user_id, :course_id, :client_session_id)
                """
            ),
            {
                "id": session_id,
                "student_user_id": student_user_id,
                "course_id": course_id,
                "client_session_id": client_session_id,
            },
        )
        await session.commit()
        return session_id
