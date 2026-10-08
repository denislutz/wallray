from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.adapters.persistence.pg_job_repo import PostgresJobRepository
from app.adapters.persistence.pg_user_repo import PostgresUserRepository
from app.adapters.storage.s3 import S3StorageAdapter
from app.adapters.vision_llm.anthropic import AnthropicAdapter
from app.api.deps import current_user, get_job_repo, get_storage, get_user_repo, get_vision_llm
from app.api.schemas import ReportItem, ReportStatus, VerificationItem
from app.application.get_report import GetReport, JobNotFoundError
from app.application.list_jobs import ResolvedJob

router = APIRouter(tags=["report"])


def _to_report_item(r: ResolvedJob) -> ReportItem:
    return ReportItem(
        id=r.id,
        status=ReportStatus(r.status),
        created_at=r.created_at,
        description=r.description,
        name=r.name,
        thumbnail_url=r.thumbnail_url,
        defect_type=r.defect_type,
        report_url=r.report_url,
        severity=r.severity,
        expert_notes=r.expert_notes,
        request_expert_review=r.request_expert_review,
        assigned_expert_email=r.assigned_expert_email,
        photo_urls=r.photo_urls,
        photo_thumb_urls=r.photo_thumb_urls,
        summary=r.summary,
        verification_items=[VerificationItem(**item) for item in r.verification_items or []]
        or None,
    )


@router.get("/report/{job_id}", response_model=ReportItem)
async def get_report(
    job_id: str,
    user: Annotated[dict[str, str], Depends(current_user)],
    job_repo: Annotated[PostgresJobRepository, Depends(get_job_repo)],
    storage: Annotated[S3StorageAdapter, Depends(get_storage)],
    user_repo: Annotated[PostgresUserRepository, Depends(get_user_repo)],
    vision_llm: Annotated[AnthropicAdapter, Depends(get_vision_llm)],
) -> ReportItem:
    try:
        resolved = await GetReport(storage, job_repo, user_repo, vision_llm).execute(
            job_id, str(user["sub"])
        )
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    return _to_report_item(resolved)
