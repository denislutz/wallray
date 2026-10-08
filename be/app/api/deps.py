from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.email.resend import ResendAdapter
from app.adapters.persistence.pg_job_repo import PostgresJobRepository
from app.adapters.persistence.pg_user_repo import PostgresUserRepository
from app.adapters.renderer.xhtml2pdf import Xhtml2pdfAdapter
from app.adapters.storage.s3 import S3StorageAdapter
from app.core.config import settings
from app.core.container import Container
from app.core.db import get_session
from app.domain.ports.vision_llm import VisionLLMPort
from app.domain.user import User, UserRole

_bearer = HTTPBearer()


def derive_role(email: str) -> UserRole:
    lowered = email.lower()
    if lowered in settings.admin_emails_set:
        return UserRole.admin
    if lowered in settings.expert_review_emails_set:
        return UserRole.expert_review
    return UserRole.customer


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


def get_storage(
    container: Annotated[Container, Depends(get_container)],
) -> S3StorageAdapter:
    return container.storage


def get_vision_llm(
    request: Request,
    container: Annotated[Container, Depends(get_container)],
) -> VisionLLMPort:
    if settings.debug and request.headers.get("x-e2e-fake-ai") == "1":
        return container.fake_vision_llm
    return container.vision_llm


def get_renderer(
    container: Annotated[Container, Depends(get_container)],
) -> Xhtml2pdfAdapter:
    return container.renderer


def get_email(
    container: Annotated[Container, Depends(get_container)],
) -> ResendAdapter:
    return container.email


async def get_job_repo(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PostgresJobRepository:
    return PostgresJobRepository(session)


async def get_user_repo(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PostgresUserRepository:
    return PostgresUserRepository(session)


async def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    try:
        payload: dict[str, object] = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
    email = str(payload.get("email", ""))
    role = derive_role(email)
    resolved = await PostgresUserRepository(session).upsert(
        User(id=str(payload["sub"]), email=email, role=role)
    )
    return {**payload, "sub": resolved.id}


async def current_user_from_query(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    token = request.query_params.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        payload: dict[str, object] = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
    email = str(payload.get("email", ""))
    role = derive_role(email)
    resolved = await PostgresUserRepository(session).upsert(
        User(id=str(payload["sub"]), email=email, role=role)
    )
    return {**payload, "sub": resolved.id}


def require_role(*roles: UserRole):  # type: ignore[no-untyped-def]
    async def _dep(
        user_payload: Annotated[dict[str, object], Depends(current_user)],
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> dict[str, object]:
        db_user = await PostgresUserRepository(session).get(str(user_payload["sub"]))
        if db_user is None or db_user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return user_payload

    return _dep
