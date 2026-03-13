from db.repositories.cache import get_cached_answer, set_cached_answer


async def try_get_cached_answer(*, namespace: str, course_id: str, question: str) -> str | None:
    return await get_cached_answer(namespace=namespace, course_id=course_id, question=question)


async def cache_answer(*, namespace: str, course_id: str, question: str, answer: str) -> None:
    await set_cached_answer(namespace=namespace, course_id=course_id, question=question, answer=answer)
