import sqlalchemy as sa

from core.database import SessionLocal


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
    async with SessionLocal() as session:
        result = await session.execute(query, {"student_user_id": student_user_id, "course_id": course_id})
        row = result.fetchone()
        return dict(row._mapping) if row else None


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
    async with SessionLocal() as session:
        result = await session.execute(query, {"staff_user_id": staff_user_id, "course_id": course_id})
        row = result.fetchone()
        return dict(row._mapping) if row else None


async def create_subject(*, id: str, university_id: str, faculty_id: str, semester_id: str, course_code: str, course_name: str) -> None:
    query = sa.text(
        """
        INSERT INTO courses (id, university_id, faculty_id, semester_id, course_code, course_name, is_active)
        VALUES (:id, :university_id, :faculty_id, :semester_id, :course_code, :course_name, TRUE)
        ON CONFLICT (id) DO UPDATE
        SET university_id = EXCLUDED.university_id,
            faculty_id = EXCLUDED.faculty_id,
            semester_id = EXCLUDED.semester_id,
            course_code = EXCLUDED.course_code,
            course_name = EXCLUDED.course_name,
            is_active = TRUE
        """
    )
    async with SessionLocal() as session:
        await session.execute(
            query,
            {
                "id": id,
                "university_id": university_id,
                "faculty_id": faculty_id,
                "semester_id": semester_id,
                "course_code": course_code,
                "course_name": course_name,
            },
        )
        await session.commit()
