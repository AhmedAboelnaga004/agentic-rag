from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from core.dependencies import get_optional_token_payload
from db.repositories.messages import append_messages
from db.repositories.sessions import get_or_create_session
from db.repositories.subjects import get_course_context_for_student
from db.repositories.usage import upsert_usage_log
from models.chat import ChatRequest, ChatResponse, ValidateContextRequest, ValidateContextResponse
from services.rag.agent import run_agent


router = APIRouter(prefix="/student", tags=["student"])
compat_router = APIRouter(prefix="/api", tags=["student-compat"])



def _estimate_chat_cost_usd(prompt: str, answer: str) -> float:
    approx_input_tokens = max(1, len(prompt) // 4)
    approx_output_tokens = max(1, len(answer) // 4)
    return (approx_input_tokens / 1_000_000) * 0.35 + (approx_output_tokens / 1_000_000) * 1.05


async def _validate_context_impl(req: ValidateContextRequest) -> ValidateContextResponse:
    context = await get_course_context_for_student(student_user_id=req.user_id, course_id=req.course_id)
    if not context:
        raise HTTPException(
            status_code=403,
            detail="Invalid credentials: this student is not actively enrolled in the selected course.",
        )

    if context["university_id"] != req.university_id:
        raise HTTPException(status_code=400, detail="Invalid context: university does not match this course enrollment.")
    if context["faculty_id"] != req.faculty_id:
        raise HTTPException(status_code=400, detail="Invalid context: faculty does not match this course enrollment.")
    if context["semester_id"] != req.semester:
        raise HTTPException(status_code=400, detail="Invalid context: semester does not match this course enrollment.")
    if context["course_code"] != req.course_code:
        raise HTTPException(status_code=400, detail="Invalid context: course code does not match this course.")
    if context["course_name"] != req.course_name:
        raise HTTPException(status_code=400, detail="Invalid context: course name does not match this course.")

    session_id = await get_or_create_session(student_user_id=req.user_id, course_id=req.course_id)
    return ValidateContextResponse(ok=True, sessionId=session_id)


async def _chat_impl(req: ChatRequest, background_tasks: BackgroundTasks) -> ChatResponse:
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message required")

    context = await get_course_context_for_student(student_user_id=req.user_id, course_id=req.course_id)
    if not context:
        raise HTTPException(status_code=403, detail="Access denied: student is not actively enrolled in this course.")

    session_id = await get_or_create_session(
        student_user_id=req.user_id,
        course_id=req.course_id,
        client_session_id=req.sessionId or None,
    )

    try:
        output = await run_agent(
            message=req.message,
            session_id=session_id,
            namespace=context["pinecone_namespace"],
            course_id=context["course_id"],
            course_name=context["course_name"],
        )
        if not output or not output.strip():
            return ChatResponse(
                answer="I apologize, but I couldn't generate a proper response. Could you please rephrase your question?",
                sessionId=session_id,
            )

        background_tasks.add_task(
            append_messages,
            session_id=session_id,
            course_id=req.course_id,
            human_content=req.message,
            ai_content=output,
        )
        background_tasks.add_task(
            upsert_usage_log,
            university_id=context["university_id"],
            chat_queries_inc=1,
            message_count_inc=2,
            estimated_cost_usd_inc=_estimate_chat_cost_usd(req.message, output),
        )
        return ChatResponse(answer=output, sessionId=session_id)
    except Exception as exc:
        await upsert_usage_log(university_id=context["university_id"], failed_requests_inc=1)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/validate-context", response_model=ValidateContextResponse)
async def validate_context(req: ValidateContextRequest, _: dict | None = Depends(get_optional_token_payload)):
    return await _validate_context_impl(req)


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, background_tasks: BackgroundTasks, _: dict | None = Depends(get_optional_token_payload)):
    return await _chat_impl(req, background_tasks)


@compat_router.post("/validate-context", response_model=ValidateContextResponse, include_in_schema=False)
async def validate_context_compat(req: ValidateContextRequest):
    return await _validate_context_impl(req)


@compat_router.post("/chat", response_model=ChatResponse, include_in_schema=False)
async def chat_compat(req: ChatRequest, background_tasks: BackgroundTasks):
    return await _chat_impl(req, background_tasks)
