from db.repositories import subjects as subjects_repo
from models.university import SubjectCreate


async def create_subject(payload: SubjectCreate) -> None:
    await subjects_repo.create_subject(
        id=payload.id,
        university_id=payload.university_id,
        faculty_id=payload.faculty_id,
        semester_id=payload.semester_id,
        course_code=payload.course_code,
        course_name=payload.course_name,
    )
