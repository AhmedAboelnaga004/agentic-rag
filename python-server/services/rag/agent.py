from agent import run_agent as _legacy_run_agent
from services.rag.cache import cache_answer, try_get_cached_answer
from services.rag.retriever import build_effective_query


async def run_agent(
    *,
    message: str,
    session_id: str,
    namespace: str,
    course_id: str,
    course_name: str,
) -> str:
    effective_query = build_effective_query(message)
    cached = await try_get_cached_answer(namespace=namespace, course_id=course_id, question=effective_query)
    if cached:
        return cached

    answer = await _legacy_run_agent(
        message=effective_query,
        session_id=session_id,
        namespace=namespace,
        course_id=course_id,
        course_name=course_name,
    )
    if answer:
        await cache_answer(namespace=namespace, course_id=course_id, question=effective_query, answer=answer)
    return answer
