from pydantic import BaseModel


class DocumentUpload(BaseModel):
    user_id: str
    university_id: str
    faculty_id: str
    semester: str
    course_id: str
    course_code: str
    course_name: str
    doc_title: str
    doc_type: str
    technique: str = "gemini"


class DocumentStatus(BaseModel):
    ok: bool
    chunks: int
    documentId: int
