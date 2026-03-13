import asyncio
import sys
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from core.config import settings
from core.database import init_db
from routers.admin import router as admin_router
from routers.auth import router as auth_router
from routers.instructor import compat_router as instructor_compat_router
from routers.instructor import router as instructor_router
from routers.student import compat_router as student_compat_router
from routers.student import router as student_router
from workers.ingestion_worker import start_worker, stop_worker


if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    await start_worker()
    try:
        yield
    finally:
        await stop_worker()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(instructor_router)
app.include_router(student_router)
app.include_router(instructor_compat_router)
app.include_router(student_compat_router)


if __name__ == "__main__":
    import uvicorn

    if sys.platform.startswith("win"):
        async def _serve_windows() -> None:
            config = uvicorn.Config("main:app", host=settings.app_host, port=settings.app_port, reload=False)
            server = uvicorn.Server(config)
            await server.serve()

        try:
            asyncio.run(_serve_windows(), loop_factory=asyncio.SelectorEventLoop)
        except TypeError:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            uvicorn.run("main:app", host=settings.app_host, port=settings.app_port, reload=False)
    else:
        uvicorn.run("main:app", host=settings.app_host, port=settings.app_port, reload=False)
