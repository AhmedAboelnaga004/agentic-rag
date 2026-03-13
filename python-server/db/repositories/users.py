import sqlalchemy as sa

from core.database import SessionLocal


async def get_user_by_id(user_id: str) -> dict | None:
    query = sa.text(
        """
        SELECT id, university_id, full_name, email, role, is_active
        FROM users
        WHERE id = :user_id
        LIMIT 1
        """
    )
    async with SessionLocal() as session:
        result = await session.execute(query, {"user_id": user_id})
        row = result.fetchone()
        return dict(row._mapping) if row else None


async def create_user(*, user_id: str, university_id: str, role: str, full_name: str | None = None, email: str | None = None) -> None:
    query = sa.text(
        """
        INSERT INTO users (id, university_id, full_name, email, role, is_active)
        VALUES (:id, :university_id, :full_name, :email, :role, TRUE)
        ON CONFLICT (id) DO UPDATE
        SET university_id = EXCLUDED.university_id,
            full_name = COALESCE(EXCLUDED.full_name, users.full_name),
            email = COALESCE(EXCLUDED.email, users.email),
            role = EXCLUDED.role,
            is_active = TRUE
        """
    )
    async with SessionLocal() as session:
        await session.execute(
            query,
            {
                "id": user_id,
                "university_id": university_id,
                "full_name": full_name,
                "email": email,
                "role": role,
            },
        )
        await session.commit()
