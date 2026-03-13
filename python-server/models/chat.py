from pydantic import BaseModel


class Source(BaseModel):
    title: str | None = None
    page: int | None = None
    section: str | None = None


class ChatRequest(BaseModel):
    message: str
    user_id: str
    sessionId: str = ""
    course_id: str


class ChatResponse(BaseModel):
    answer: str
    sessionId: str
    sources: list[Source] = []


class ValidateContextRequest(BaseModel):
    user_id: str
    university_id: str
    faculty_id: str
    semester: str
    course_id: str
    course_code: str
    course_name: str


class ValidateContextResponse(BaseModel):
    ok: bool
    sessionId: str
