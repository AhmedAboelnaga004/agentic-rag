from db.repositories.users import create_user, get_user_by_id


async def get_user(user_id: str) -> dict | None:
    return await get_user_by_id(user_id)


async def upsert_user(*, user_id: str, university_id: str, role: str, full_name: str | None = None, email: str | None = None) -> None:
    await create_user(
        user_id=user_id,
        university_id=university_id,
        role=role,
        full_name=full_name,
        email=email,
    )
