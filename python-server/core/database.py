from pathlib import Path
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import settings


engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=300,
    echo=False,
)

SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


def migration_files() -> list[Path]:
    root = Path(__file__).resolve().parents[1]
    migrations_dir = root / "db" / "migrations"
    if not migrations_dir.exists():
        return []
    return sorted(migrations_dir.glob("*.sql"))


async def run_migrations() -> None:
    direct_engine = create_async_engine(
        settings.database_url_direct,
        pool_pre_ping=True,
        echo=False,
    )
    async with direct_engine.begin() as conn:
        for file in migration_files():
            sql = file.read_text(encoding="utf-8")
            statements = [stmt.strip() for stmt in sql.split(";") if stmt.strip()]
            for stmt in statements:
                await conn.exec_driver_sql(stmt)
    await direct_engine.dispose()


async def init_db() -> None:
    await run_migrations()


async def get_db_session() -> AsyncSession:
    async with SessionLocal() as session:
        yield session
