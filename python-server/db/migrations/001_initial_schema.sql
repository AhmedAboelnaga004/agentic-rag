CREATE TABLE IF NOT EXISTS universities (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    pinecone_namespace  TEXT NOT NULL UNIQUE,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS faculties (
    id              TEXT PRIMARY KEY,
    university_id   TEXT NOT NULL REFERENCES universities(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS semesters (
    id              TEXT PRIMARY KEY,
    university_id   TEXT NOT NULL REFERENCES universities(id) ON DELETE CASCADE,
    label           TEXT NOT NULL,
    starts_on       DATE,
    ends_on         DATE,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

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

CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,
    university_id   TEXT NOT NULL REFERENCES universities(id) ON DELETE CASCADE,
    full_name       TEXT,
    email           TEXT UNIQUE,
    role            TEXT NOT NULL CHECK (role IN ('student', 'professor', 'admin')),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS enrollments (
    id                  BIGSERIAL PRIMARY KEY,
    student_user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course_id           TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    status              TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'dropped')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (student_user_id, course_id)
);

CREATE TABLE IF NOT EXISTS sessions (
    id                  TEXT PRIMARY KEY,
    student_user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course_id           TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    client_session_id   TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (student_user_id, course_id)
);

CREATE TABLE IF NOT EXISTS documents (
    id                  BIGSERIAL PRIMARY KEY,
    university_id       TEXT NOT NULL,
    faculty_id          TEXT NOT NULL,
    semester_id         TEXT NOT NULL,
    course_id           TEXT NOT NULL,
    course_code         TEXT NOT NULL,
    course_name         TEXT NOT NULL,
    uploaded_by_user_id TEXT NOT NULL,
    doc_title           TEXT NOT NULL,
    doc_type            TEXT NOT NULL,
    technique           TEXT NOT NULL,
    file_hash           CHAR(64) NOT NULL,
    original_filename   TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'processing' CHECK (status IN ('processing', 'ready', 'failed')),
    chunk_count         INTEGER NOT NULL DEFAULT 0,
    error_message       TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS messages (
    id          BIGSERIAL PRIMARY KEY,
    session_id  TEXT NOT NULL,
    course_id   TEXT NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

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

CREATE TABLE IF NOT EXISTS semantic_cache (
    cache_key       CHAR(64) PRIMARY KEY,
    namespace       TEXT NOT NULL,
    course_id       TEXT NOT NULL,
    question        TEXT NOT NULL,
    answer          TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_documents_course_hash ON documents (course_id, file_hash);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages (session_id, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_courses_university ON courses (university_id);
CREATE INDEX IF NOT EXISTS idx_enrollments_student ON enrollments (student_user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_student_course ON sessions (student_user_id, course_id);
CREATE INDEX IF NOT EXISTS idx_usage_logs_uni_date ON usage_logs (university_id, usage_date DESC);
CREATE INDEX IF NOT EXISTS idx_semantic_cache_lookup ON semantic_cache (namespace, course_id);
