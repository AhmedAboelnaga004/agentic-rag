from pydantic import BaseModel


class LoginRequest(BaseModel):
    user_id: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    role: str


class LogoutResponse(BaseModel):
    ok: bool = True
