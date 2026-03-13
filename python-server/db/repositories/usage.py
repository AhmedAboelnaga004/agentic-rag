from datetime import date

import sqlalchemy as sa

from core.database import SessionLocal


async def upsert_usage_log(
    *,
    university_id: str,
    usage_date: date | None = None,
    chat_queries_inc: int = 0,
    ingest_requests_inc: int = 0,
    message_count_inc: int = 0,
    llm_input_tokens_inc: int = 0,
    llm_output_tokens_inc: int = 0,
    estimated_cost_usd_inc: float = 0.0,
    failed_requests_inc: int = 0,
) -> None:
    usage_date = usage_date or date.today()
    query = sa.text(
        """
        INSERT INTO usage_logs (
            university_id,
            usage_date,
            chat_queries,
            ingest_requests,
            message_count,
            llm_input_tokens,
            llm_output_tokens,
            estimated_cost_usd,
            failed_requests,
            updated_at
        )
        VALUES (
            :university_id,
            :usage_date,
            :chat_queries_inc,
            :ingest_requests_inc,
            :message_count_inc,
            :llm_input_tokens_inc,
            :llm_output_tokens_inc,
            :estimated_cost_usd_inc,
            :failed_requests_inc,
            NOW()
        )
        ON CONFLICT (university_id, usage_date)
        DO UPDATE SET
            chat_queries = usage_logs.chat_queries + EXCLUDED.chat_queries,
            ingest_requests = usage_logs.ingest_requests + EXCLUDED.ingest_requests,
            message_count = usage_logs.message_count + EXCLUDED.message_count,
            llm_input_tokens = usage_logs.llm_input_tokens + EXCLUDED.llm_input_tokens,
            llm_output_tokens = usage_logs.llm_output_tokens + EXCLUDED.llm_output_tokens,
            estimated_cost_usd = usage_logs.estimated_cost_usd + EXCLUDED.estimated_cost_usd,
            failed_requests = usage_logs.failed_requests + EXCLUDED.failed_requests,
            updated_at = NOW()
        """
    )
    async with SessionLocal() as session:
        await session.execute(
            query,
            {
                "university_id": university_id,
                "usage_date": usage_date,
                "chat_queries_inc": chat_queries_inc,
                "ingest_requests_inc": ingest_requests_inc,
                "message_count_inc": message_count_inc,
                "llm_input_tokens_inc": llm_input_tokens_inc,
                "llm_output_tokens_inc": llm_output_tokens_inc,
                "estimated_cost_usd_inc": estimated_cost_usd_inc,
                "failed_requests_inc": failed_requests_inc,
            },
        )
        await session.commit()


async def list_usage(university_id: str) -> list[dict]:
    query = sa.text(
        """
        SELECT usage_date, chat_queries, ingest_requests, message_count,
               llm_input_tokens, llm_output_tokens, estimated_cost_usd, failed_requests
        FROM usage_logs
        WHERE university_id = :university_id
        ORDER BY usage_date DESC
        LIMIT 60
        """
    )
    async with SessionLocal() as session:
        result = await session.execute(query, {"university_id": university_id})
        return [dict(row._mapping) for row in result.fetchall()]
