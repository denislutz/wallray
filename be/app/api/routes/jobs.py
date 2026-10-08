from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.adapters.email.resend import ResendAdapter
from app.adapters.persistence.pg_job_repo import PostgresJobRepository
from app.adapters.persistence.pg_user_repo import PostgresUserRepository
from app.adapters.renderer.xhtml2pdf import Xhtml2pdfAdapter
from app.adapters.storage.s3 import S3StorageAdapter
from app.adapters.vision_llm.anthropic import AnthropicAdapter
from app.api.deps import (
    current_user,
    get_email,
    get_job_repo,
    get_renderer,
    get_storage,
    get_user_repo,
    get_vision_llm,
)
from app.api.schemas import ReportItem, ReportStatus, RespondRequest, VerificationItem
from app.application.list_jobs import ListJobs, ResolvedJob
from app.application.respond_to_job import RespondToJob
from app.core.config import settings
from app.domain.job import JobStatus

router = APIRouter(tags=["jobs"])


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
        request_expert_review=r.request_expert_review,
        assigned_expert_email=r.assigned_expert_email,
        verification_items=[VerificationItem(**item) for item in r.verification_items or []]
        or None,
    )


@router.get("/jobs", response_model=list[ReportItem])
async def list_jobs(
    user: Annotated[dict[str, str], Depends(current_user)],
    job_repo: Annotated[PostgresJobRepository, Depends(get_job_repo)],
    storage: Annotated[S3StorageAdapter, Depends(get_storage)],
    user_repo: Annotated[PostgresUserRepository, Depends(get_user_repo)],
) -> list[ReportItem]:
    resolved = await ListJobs(storage, job_repo, user_repo).execute(str(user["sub"]))
    return [_to_report_item(r) for r in resolved]


@router.post("/jobs/{job_id}/respond")
async def respond_to_job(
    job_id: str,
    body: RespondRequest,
    background_tasks: BackgroundTasks,
    user: Annotated[dict[str, object], Depends(current_user)],
    job_repo: Annotated[PostgresJobRepository, Depends(get_job_repo)],
    user_repo: Annotated[PostgresUserRepository, Depends(get_user_repo)],
    storage: Annotated[S3StorageAdapter, Depends(get_storage)],
    renderer: Annotated[Xhtml2pdfAdapter, Depends(get_renderer)],
    email: Annotated[ResendAdapter, Depends(get_email)],
    vision_llm: Annotated[AnthropicAdapter, Depends(get_vision_llm)],
) -> dict[str, bool]:
    job = await job_repo.get(job_id)
    if job is None or job.user_id != str(user["sub"]):
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.awaiting_customer_input:
        raise HTTPException(status_code=409, detail="Job is not awaiting a customer response")
    if body.request_expert_review and not body.assigned_expert_id:
        raise HTTPException(
            status_code=422, detail="An expert must be selected when requesting expert review"
        )

    await job_repo.update_status(job_id, JobStatus.processing)

    respond = RespondToJob(
        storage=storage,
        job_repo=job_repo,
        user_repo=user_repo,
        vision_llm=vision_llm,
        renderer=renderer,
        email=email,
        fe_base_url=settings.fe_base_url,
    )
    background_tasks.add_task(
        respond.run,
        job_id,
        str(user["sub"]),
        body.reply,
        body.request_expert_review,
        body.assigned_expert_id,
    )
    return {"ok": True}
