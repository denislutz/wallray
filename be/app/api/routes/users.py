from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.api.deps import current_user

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
async def me(user: Annotated[dict[str, Any], Depends(current_user)]) -> dict[str, Any]:
    return user
