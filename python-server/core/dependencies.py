from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, status

from core.security import decode_token


async def get_optional_token_payload(authorization: str | None = Header(default=None)) -> dict | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization header")
    return decode_token(token)


async def get_current_user(payload: dict | None = Depends(get_optional_token_payload)) -> dict:
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return payload



def require_roles(*allowed_roles: str) -> Callable:
    async def _dependency(user: dict = Depends(get_current_user)) -> dict:
        role = user.get("role")
        if role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return _dependency
