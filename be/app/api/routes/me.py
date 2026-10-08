from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.adapters.persistence.pg_user_repo import PostgresUserRepository
from app.api.deps import current_user, get_user_repo
from app.api.schemas import LanguageUpdate, MeResponse

router = APIRouter(tags=["me"])

_ALLOWED_LANGUAGES = {"en", "de", "ru", "el"}


@router.get("/me", response_model=MeResponse)
async def get_me(
    user_payload: Annotated[dict[str, object], Depends(current_user)],
    user_repo: Annotated[PostgresUserRepository, Depends(get_user_repo)],
) -> MeResponse:
    db_user = await user_repo.get(str(user_payload["sub"]))
    return MeResponse(
        role=db_user.role.value if db_user else "customer",
        email=db_user.email if db_user else str(user_payload.get("email", "")),
        preferred_language=db_user.preferred_language if db_user else "en",
    )


@router.patch("/me/language", status_code=204)
async def update_language(
    body: LanguageUpdate,
    user_payload: Annotated[dict[str, object], Depends(current_user)],
    user_repo: Annotated[PostgresUserRepository, Depends(get_user_repo)],
) -> None:
    if body.language not in _ALLOWED_LANGUAGES:
        raise HTTPException(status_code=422, detail=f"Unsupported language: {body.language}")
    await user_repo.update_language(str(user_payload["sub"]), body.language)
