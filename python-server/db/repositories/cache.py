import hashlib
import sqlalchemy as sa

from core.database import SessionLocal



def _semantic_key(namespace: str, course_id: str, question: str) -> str:
    return hashlib.sha256(f"{namespace}|{course_id}|{question.strip().lower()}".encode("utf-8")).hexdigest()


async def get_cached_answer(*, namespace: str, course_id: str, question: str) -> str | None:
    key = _semantic_key(namespace, course_id, question)
    query = sa.text("SELECT answer FROM semantic_cache WHERE cache_key = :cache_key LIMIT 1")
    async with SessionLocal() as session:
        result = await session.execute(query, {"cache_key": key})
        row = result.fetchone()
        return str(row.answer) if row else None


async def set_cached_answer(*, namespace: str, course_id: str, question: str, answer: str) -> None:
    key = _semantic_key(namespace, course_id, question)
    query = sa.text(
        """
        INSERT INTO semantic_cache (cache_key, namespace, course_id, question, answer)
        VALUES (:cache_key, :namespace, :course_id, :question, :answer)
        ON CONFLICT (cache_key) DO UPDATE
        SET answer = EXCLUDED.answer,
            updated_at = NOW()
        """
    )
    async with SessionLocal() as session:
        await session.execute(
            query,
            {
                "cache_key": key,
                "namespace": namespace,
                "course_id": course_id,
                "question": question,
                "answer": answer,
            },
        )
        await session.commit()
