from pydantic import BaseModel


class SubjectCreate(BaseModel):
    id: str
    university_id: str
    faculty_id: str
    semester_id: str
    course_code: str
    course_name: str


class EnrollmentCreate(BaseModel):
    student_user_id: str
    course_id: str
