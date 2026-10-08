from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.orm_models import UserRow
from app.domain.user import User, UserRole


def _row_to_user(row: UserRow) -> User:
    return User(
        id=row.id,
        email=row.email,
        report_count=row.report_count,
        role=UserRole(row.role),
        preferred_language=row.preferred_language,
    )


class PostgresUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: str) -> User | None:
        result = await self._session.execute(select(UserRow).where(UserRow.id == user_id))
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return _row_to_user(row)

    async def upsert(self, user: User) -> User:
        result = await self._session.execute(select(UserRow).where(UserRow.id == user.id))
        row = result.scalar_one_or_none()
        if row is None:
            # Fall back to email lookup — handles dev-login tokens whose fixed ID
            # differs from the real UUID assigned during OTP registration. The
            # existing row's id is kept (jobs/otp rows reference it by id), so the
            # resolved user returned here may carry a different id than requested.
            email_result = await self._session.execute(
                select(UserRow).where(UserRow.email == user.email)
            )
            row = email_result.scalar_one_or_none()
        if row is None:
            row = UserRow(id=user.id, email=user.email, role=user.role.value)
            self._session.add(row)
        else:
            row.email = user.email
            row.role = user.role.value
        await self._session.commit()
        await self._session.refresh(row)
        return _row_to_user(row)

    async def increment_count(self, user_id: str) -> None:
        row = await self._session.get(UserRow, user_id)
        if row is not None:
            row.report_count += 1
            await self._session.commit()

    async def update_language(self, user_id: str, language: str) -> None:
        await self._session.execute(
            update(UserRow).where(UserRow.id == user_id).values(preferred_language=language)
        )
        await self._session.commit()

    async def get_or_create_by_email(self, email: str, role: UserRole) -> User:
        result = await self._session.execute(select(UserRow).where(UserRow.email == email))
        row = result.scalar_one_or_none()
        if row is None:
            row = UserRow(id=str(uuid4()), email=email, role=role.value)
            self._session.add(row)
        else:
            row.role = role.value
        await self._session.commit()
        return _row_to_user(row)

    async def get_by_emails(self, emails: list[str]) -> list[User]:
        if not emails:
            return []
        result = await self._session.execute(select(UserRow).where(UserRow.email.in_(emails)))
        return [_row_to_user(row) for row in result.scalars()]
