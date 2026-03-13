from fastapi import APIRouter, Depends

from core.dependencies import require_roles
from db.repositories.usage import list_usage
from models.university import SubjectCreate
from services.university.subjects import create_subject


router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/subjects")
async def create_subject_endpoint(payload: SubjectCreate, _: dict = Depends(require_roles("admin"))):
    await create_subject(payload)
    return {"ok": True}


@router.get("/usage/{university_id}")
async def get_usage(university_id: str, _: dict = Depends(require_roles("admin"))):
    rows = await list_usage(university_id)
    return {"rows": rows}
