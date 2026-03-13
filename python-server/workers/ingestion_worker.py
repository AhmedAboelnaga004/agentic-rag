import asyncio
from dataclasses import dataclass
from typing import Any

from services.ingestion.pipeline import ingest_document


@dataclass
class IngestionJob:
    payload: dict[str, Any]


_queue: asyncio.Queue[IngestionJob] = asyncio.Queue()
_worker_task: asyncio.Task | None = None


async def enqueue_ingestion(payload: dict[str, Any]) -> None:
    await _queue.put(IngestionJob(payload=payload))


async def _worker_loop() -> None:
    while True:
        job = await _queue.get()
        try:
            await ingest_document(**job.payload)
        except Exception as exc:
            print(f"[IngestionWorker] Job failed: {exc}")
        finally:
            _queue.task_done()


async def start_worker() -> None:
    global _worker_task
    if _worker_task and not _worker_task.done():
        return
    _worker_task = asyncio.create_task(_worker_loop(), name="ingestion-worker")


async def stop_worker() -> None:
    global _worker_task
    if not _worker_task:
        return
    _worker_task.cancel()
    try:
        await _worker_task
    except asyncio.CancelledError:
        pass
    _worker_task = None
