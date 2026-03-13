"""
database.py — Async SQLAlchemy engine + table definitions for Neon Postgres.

Tables:
  • universities — admin-managed list of contracted institutions
  • faculties    — admin-managed faculties per university
  • semesters    — admin-managed semesters (controls which are "live")
  • documents    — lightweight metadata row per ingested PDF (~200 bytes).
                   SHA-256 hash used for deduplication within a course.
  • messages     — persistent chat history per session (Option B: written in
                   background after response is sent, so zero latency impact).
"""

import os
import uuid
from datetime import date
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# ── Engine (uses pooler URL for the app runtime) ──────────────────────────────
# pool_pre_ping=True  — re-validates connection before use; handles Neon cold-start SSL drops.
# pool_recycle=300    — recycle connections every 5 min (before Neon's idle timeout).
engine = create_async_engine(
    os.environ["DATABASE_URL"],       # postgresql+psycopg:// pooler URL
    pool_pre_ping=True,
    pool_recycle=300,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# ── DDL strings (CREATE TABLE IF NOT EXISTS — safe to run on every startup) ───

_CREATE_DOCUMENTS = """
CREATE TABLE IF NOT EXISTS documents (
    id               BIGSERIAL PRIMARY KEY,
    university_id    TEXT        NOT NULL,
    faculty_id       TEXT        NOT NULL,
    semester         TEXT        NOT NULL,
    course_id        TEXT        NOT NULL,
    course_code      TEXT        NOT NULL,
    course_name      TEXT        NOT NULL,
    doc_title        TEXT        NOT NULL,
    doc_type         TEXT        NOT NULL,
    technique        TEXT        NOT NULL,
    file_hash        CHAR(64)    NOT NULL,
    original_filename TEXT       NOT NULL,
    chunk_count      INTEGER,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

# Unique index on (course_id, file_hash) for deduplication checks during ingestion.
_CREATE_DOCUMENTS_UNIQUE_IDX = """
CREATE UNIQUE INDEX IF NOT EXISTS uq_documents_course_hash
    ON documents (course_id, file_hash);
"""

_CREATE_MESSAGES = """
CREATE TABLE IF NOT EXISTS messages (
    id          BIGSERIAL PRIMARY KEY,
    session_id  TEXT        NOT NULL,
    course_id   TEXT        NOT NULL,
    role        TEXT        NOT NULL,
    content     TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_CREATE_MESSAGES_IDX = """
CREATE INDEX IF NOT EXISTS idx_messages_session
    ON messages (session_id, created_at ASC);
"""

_CREATE_UNIVERSITIES = """
CREATE TABLE IF NOT EXISTS universities (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    pinecone_namespace  TEXT NOT NULL UNIQUE,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_CREATE_FACULTIES = """
CREATE TABLE IF NOT EXISTS faculties (
    id              TEXT PRIMARY KEY,
    university_id   TEXT NOT NULL REFERENCES universities(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_CREATE_SEMESTERS = """
CREATE TABLE IF NOT EXISTS semesters (
    id              TEXT PRIMARY KEY,
    university_id   TEXT NOT NULL REFERENCES universities(id) ON DELETE CASCADE,
    label           TEXT NOT NULL,
    starts_on       DATE,
    ends_on         DATE,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_CREATE_COURSES = """
CREATE TABLE IF NOT EXISTS courses (
    id              TEXT PRIMARY KEY,
    university_id   TEXT NOT NULL REFERENCES universities(id) ON DELETE CASCADE,
    faculty_id      TEXT NOT NULL REFERENCES faculties(id) ON DELETE RESTRICT,
    semester_id     TEXT NOT NULL REFERENCES semesters(id) ON DELETE RESTRICT,
    course_code     TEXT NOT NULL,
    course_name     TEXT NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,
    university_id   TEXT NOT NULL REFERENCES universities(id) ON DELETE CASCADE,
    full_name       TEXT,
    email           TEXT UNIQUE,
    role            TEXT NOT NULL CHECK (role IN ('student', 'professor', 'admin')),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_CREATE_ENROLLMENTS = """
CREATE TABLE IF NOT EXISTS enrollments (
    id                  BIGSERIAL PRIMARY KEY,
    student_user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course_id           TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    status              TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'dropped')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (student_user_id, course_id)
);
"""

_CREATE_SESSIONS = """
CREATE TABLE IF NOT EXISTS sessions (
    id                  TEXT PRIMARY KEY,
    student_user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course_id           TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    client_session_id   TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (student_user_id, course_id)
);
"""

_CREATE_USAGE_LOGS = """
CREATE TABLE IF NOT EXISTS usage_logs (
    id                  BIGSERIAL PRIMARY KEY,
    university_id       TEXT NOT NULL REFERENCES universities(id) ON DELETE CASCADE,
    usage_date          DATE NOT NULL,
    chat_queries        INTEGER NOT NULL DEFAULT 0,
    ingest_requests     INTEGER NOT NULL DEFAULT 0,
    message_count       INTEGER NOT NULL DEFAULT 0,
    llm_input_tokens    INTEGER NOT NULL DEFAULT 0,
    llm_output_tokens   INTEGER NOT NULL DEFAULT 0,
    estimated_cost_usd  DOUBLE PRECISION NOT NULL DEFAULT 0,
    failed_requests     INTEGER NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (university_id, usage_date)
);
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_courses_university ON courses (university_id)",
    "CREATE INDEX IF NOT EXISTS idx_enrollments_student ON enrollments (student_user_id)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_student_course ON sessions (student_user_id, course_id)",
    "CREATE INDEX IF NOT EXISTS idx_usage_logs_uni_date ON usage_logs (university_id, usage_date DESC)",
]


# ── init_db ───────────────────────────────────────────────────────────────────

async def init_db() -> None:
    """
    Create tables and indexes if they don't already exist.
    Uses DATABASE_URL_DIRECT (non-pooler) for DDL to avoid pgBouncer
    transaction-mode limitations.  Falls back to DATABASE_URL if the
    direct URL is not configured.
    """
    direct_url = os.environ.get("DATABASE_URL_DIRECT") or os.environ["DATABASE_URL"]

    direct_engine = create_async_engine(
        direct_url,
        pool_pre_ping=True,
        echo=False,
    )

    async with direct_engine.begin() as conn:
        await conn.exec_driver_sql(_CREATE_UNIVERSITIES)
        await conn.exec_driver_sql(_CREATE_FACULTIES)
        await conn.exec_driver_sql(_CREATE_SEMESTERS)
        await conn.exec_driver_sql(_CREATE_COURSES)
        await conn.exec_driver_sql(_CREATE_USERS)
        await conn.exec_driver_sql(_CREATE_ENROLLMENTS)
        await conn.exec_driver_sql(_CREATE_SESSIONS)
        await conn.exec_driver_sql(_CREATE_USAGE_LOGS)
        await conn.exec_driver_sql(_CREATE_DOCUMENTS)
        await conn.exec_driver_sql(_CREATE_DOCUMENTS_UNIQUE_IDX)
        await conn.exec_driver_sql(_CREATE_MESSAGES)
        await conn.exec_driver_sql(_CREATE_MESSAGES_IDX)
        for ddl in _CREATE_INDEXES:
            await conn.exec_driver_sql(ddl)

    await direct_engine.dispose()
    print("[DB] Tables initialised ✓")


# ── Convenience helpers ────────────────────────────────────────────────────────

async def doc_exists(course_id: str, file_hash: str) -> bool:
    """Return True if a document with this hash is already in this course."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            __import__("sqlalchemy").text(
                "SELECT 1 FROM documents WHERE course_id = :cid AND file_hash = :fh LIMIT 1"
            ),
            {"cid": course_id, "fh": file_hash},
        )
        return result.fetchone() is not None


async def insert_document(
    *,
    university_id: str,
    faculty_id: str,
    semester: str,
    course_id: str,
    course_code: str,
    course_name: str,
    doc_title: str,
    doc_type: str,
    technique: str,
    file_hash: str,
    original_filename: str,
    chunk_count: int,
) -> None:
    """Insert a metadata row for a freshly ingested document."""
    import sqlalchemy as sa
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                sa.text(
                    """
                    INSERT INTO documents
                        (university_id, faculty_id, semester, course_id, course_code,
                         course_name, doc_title, doc_type, technique,
                         file_hash, original_filename, chunk_count)
                    VALUES
                        (:university_id, :faculty_id, :semester, :course_id, :course_code,
                         :course_name, :doc_title, :doc_type, :technique,
                         :file_hash, :original_filename, :chunk_count)
                    """
                ),
                {
                    "university_id":    university_id,
                    "faculty_id":       faculty_id,
                    "semester":         semester,
                    "course_id":        course_id,
                    "course_code":      course_code,
                    "course_name":      course_name,
                    "doc_title":        doc_title,
                    "doc_type":         doc_type,
                    "technique":        technique,
                    "file_hash":        file_hash,
                    "original_filename": original_filename,
                    "chunk_count":      chunk_count,
                },
            )


async def load_session_messages(session_id: str) -> list[dict]:
    """
    Load all messages for a session ordered by creation time.
    Returns list of {"role": str, "content": str}.
    """
    import sqlalchemy as sa
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            sa.text(
                """
                SELECT role, content FROM messages
                WHERE session_id = :sid
                ORDER BY created_at ASC
                """
            ),
            {"sid": session_id},
        )
        return [{"role": row.role, "content": row.content} for row in result.fetchall()]


async def append_messages(
    session_id: str,
    course_id: str,
    human_content: str,
    ai_content: str,
) -> None:
    """
    Persist one human + one AI turn.  Called as a fire-and-forget background
    task — the HTTP response is already sent before this runs.
    """
    import sqlalchemy as sa
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                sa.text(
                    """
                    INSERT INTO messages (session_id, course_id, role, content)
                    VALUES (:sid, :cid, :role, :content)
                    """
                ),
                [
                    {"sid": session_id, "cid": course_id, "role": "human",  "content": human_content},
                    {"sid": session_id, "cid": course_id, "role": "ai",     "content": ai_content},
                ],
            )


# This function to checks if a student user is actively enrolled in a specific course before chat/RAG runs.
async def get_course_context_for_student(*, student_user_id: str, course_id: str) -> dict | None:
    query = sa.text(
        """
        SELECT
            c.id AS course_id,
            c.course_code,
            c.course_name,
            c.university_id,
            c.faculty_id,
            c.semester_id,
            u.pinecone_namespace
        FROM enrollments e
        JOIN users s ON s.id = e.student_user_id
        JOIN courses c ON c.id = e.course_id
        JOIN universities u ON u.id = c.university_id
        JOIN semesters sem ON sem.id = c.semester_id
        WHERE e.student_user_id = :student_user_id
          AND e.course_id = :course_id
          AND e.status = 'active'
          AND s.role = 'student'
          AND s.is_active = TRUE
          AND c.is_active = TRUE
          AND u.is_active = TRUE
          AND sem.is_active = TRUE
        LIMIT 1
        """
    )
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            query,
            {"student_user_id": student_user_id, "course_id": course_id},
        )
        row = res.fetchone()
        if not row:
            return None
        return dict(row._mapping)


# This function to check if a staff user (professor or admin) has access to a course, used for the /ingest endpoint.
async def get_course_context_for_staff(*, staff_user_id: str, course_id: str) -> dict | None:
    query = sa.text(
        """
        SELECT
            c.id AS course_id,
            c.course_code,
            c.course_name,
            c.university_id,
            c.faculty_id,
            c.semester_id,
            u.pinecone_namespace,
            usr.role AS user_role
        FROM users usr
        JOIN courses c ON c.university_id = usr.university_id
        JOIN universities u ON u.id = c.university_id
        JOIN semesters sem ON sem.id = c.semester_id
        WHERE usr.id = :staff_user_id
          AND c.id = :course_id
          AND usr.is_active = TRUE
          AND usr.role IN ('professor', 'admin')
          AND c.is_active = TRUE
          AND u.is_active = TRUE
          AND sem.is_active = TRUE
        LIMIT 1
        """
    )
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            query,
            {"staff_user_id": staff_user_id, "course_id": course_id},
        )
        row = res.fetchone()
        if not row:
            return None
        return dict(row._mapping)


async def get_or_create_session(*, student_user_id: str, course_id: str, client_session_id: str | None = None) -> str:
    async with AsyncSessionLocal() as session:
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
            sid = row.id
            await session.execute(
                sa.text("UPDATE sessions SET updated_at = NOW() WHERE id = :sid"),
                {"sid": sid},
            )
            await session.commit()
            return sid

        sid = str(uuid.uuid4())
        await session.execute(
            sa.text(
                """
                INSERT INTO sessions (id, student_user_id, course_id, client_session_id)
                VALUES (:id, :student_user_id, :course_id, :client_session_id)
                """
            ),
            {
                "id": sid,
                "student_user_id": student_user_id,
                "course_id": course_id,
                "client_session_id": client_session_id,
            },
        )
        await session.commit()
        return sid


async def create_document_record(
    *,
    university_id: str,
    faculty_id: str,
    semester_id: str,
    course_id: str,
    uploaded_by_user_id: str,
    doc_title: str,
    doc_type: str,
    technique: str,
    file_hash: str,
    original_filename: str,
) -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            sa.text(
                """
                INSERT INTO documents
                    (university_id, faculty_id, semester, course_id,
                     doc_title, doc_type, technique,
                     file_hash, original_filename, chunk_count)
                VALUES
                    (:university_id, :faculty_id, :semester_id, :course_id,
                     :doc_title, :doc_type, :technique,
                     :file_hash, :original_filename, 0)
                RETURNING id
                """
            ),
            {
                "university_id": university_id,
                "faculty_id": faculty_id,
                "semester_id": semester_id,
                "course_id": course_id,
                "doc_title": doc_title,
                "doc_type": doc_type,
                "technique": technique,
                "file_hash": file_hash,
                "original_filename": original_filename,
                "uploaded_by_user_id": uploaded_by_user_id,
            },
        )
        row = result.fetchone()
        await session.commit()
        return int(row.id)


async def update_document_status(*, document_id: int, status: str, chunk_count: int | None = None, error_message: str | None = None) -> None:
    if status == "ready":
        await update_document_result(document_id=document_id, chunk_count=chunk_count or 0, error_message=None)
        return
    if status == "failed":
        await update_document_result(document_id=document_id, chunk_count=chunk_count or 0, error_message=error_message)
        return


async def update_document_result(*, document_id: int, chunk_count: int, error_message: str | None) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            sa.text(
                """
                UPDATE documents
                SET chunk_count = :chunk_count
                WHERE id = :document_id
                """
            ),
            {
                "chunk_count": chunk_count,
                "document_id": document_id,
            },
        )
        await session.commit()


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
    async with AsyncSessionLocal() as session:
        await session.execute(
            sa.text(
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
            ),
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
