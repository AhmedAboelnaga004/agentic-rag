from fastapi import APIRouter, HTTPException

from core.security import create_access_token
from models.auth import LoginRequest, LogoutResponse, TokenResponse
from services.university.users import get_user


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest):
    user = await get_user(payload.user_id)
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(subject=str(user["id"]), role=str(user["role"]))
    return TokenResponse(
        access_token=token,
        user_id=str(user["id"]),
        role=str(user["role"]),
    )


@router.post("/logout", response_model=LogoutResponse)
async def logout() -> LogoutResponse:
    return LogoutResponse(ok=True)
