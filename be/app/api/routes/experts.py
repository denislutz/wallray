from typing import Annotated

from fastapi import APIRouter, Depends

from app.adapters.persistence.pg_user_repo import PostgresUserRepository
from app.api.deps import current_user, get_user_repo
from app.api.schemas import ExpertItem
from app.core.config import settings

router = APIRouter(tags=["experts"])


@router.get("/experts", response_model=list[ExpertItem])
async def list_experts(
    _: Annotated[dict[str, object], Depends(current_user)],
    user_repo: Annotated[PostgresUserRepository, Depends(get_user_repo)],
) -> list[ExpertItem]:
    experts = await user_repo.get_by_emails(settings.expert_review_emails_list)
    email_map = {u.email: u for u in experts}
    return [
        ExpertItem(id=email_map[e].id, email=email_map[e].email)
        for e in settings.expert_review_emails_list
        if e in email_map
    ]
