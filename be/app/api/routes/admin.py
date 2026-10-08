from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.adapters.email.resend import ResendAdapter
from app.adapters.persistence.pg_job_repo import PostgresJobRepository
from app.adapters.persistence.pg_user_repo import PostgresUserRepository
from app.adapters.renderer.xhtml2pdf import Xhtml2pdfAdapter
from app.adapters.storage.s3 import S3StorageAdapter
from app.adapters.vision_llm.anthropic import AnthropicAdapter
from app.api.deps import (
    get_email,
    get_job_repo,
    get_renderer,
    get_storage,
    get_user_repo,
    get_vision_llm,
    require_role,
)
from app.api.schemas import ApproveRequest, ReportItem, ReportStatus, VerificationItem
from app.application.generate_report import GenerateReport
from app.application.list_jobs import ResolvedJob
from app.core.config import settings
from app.domain.job import JobStatus
from app.domain.user import UserRole

router = APIRouter(prefix="/admin", tags=["admin"])

_expert_or_admin = require_role(UserRole.expert_review, UserRole.admin)


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
        photo_urls=r.photo_urls,
        photo_thumb_urls=r.photo_thumb_urls,
        summary=r.summary,
        verification_items=[VerificationItem(**item) for item in r.verification_items or []]
        or None,
    )


@router.get("/reviews", response_model=list[ReportItem])
async def list_reviews(
    user: Annotated[dict[str, object], Depends(_expert_or_admin)],
    job_repo: Annotated[PostgresJobRepository, Depends(get_job_repo)],
    storage: Annotated[S3StorageAdapter, Depends(get_storage)],
) -> list[ReportItem]:
    jobs = await job_repo.list_by_assigned_expert(str(user["sub"]), JobStatus.expert_review)
    items = []
    for job in jobs:
        thumbnail_url: str | None = None
        if job.thumbnail_key:
            thumbnail_url = await storage.signed_url(job.thumbnail_key)
        resolved = ResolvedJob(
            id=job.id,
            status=job.status.value,
            created_at=job.created_at,
            description=job.description,
            thumbnail_url=thumbnail_url,
            defect_type=job.defect_type,
            report_url=None,
            severity=job.severity,
            expert_notes=job.expert_notes,
            name=job.name,
        )
        items.append(_to_report_item(resolved))
    return items


@router.get("/reviews/history", response_model=list[ReportItem])
async def list_all_reviews(
    user: Annotated[dict[str, object], Depends(_expert_or_admin)],
    job_repo: Annotated[PostgresJobRepository, Depends(get_job_repo)],
    storage: Annotated[S3StorageAdapter, Depends(get_storage)],
) -> list[ReportItem]:
    jobs = await job_repo.list_all_by_assigned_expert(str(user["sub"]))
    items = []
    for job in jobs:
        thumbnail_url: str | None = None
        if job.thumbnail_key:
            thumbnail_url = await storage.signed_url(job.thumbnail_key)
        report_url: str | None = None
        if job.report_key:
            report_url = await storage.signed_url(job.report_key)
        resolved = ResolvedJob(
            id=job.id,
            status=job.status.value,
            created_at=job.created_at,
            description=job.description,
            thumbnail_url=thumbnail_url,
            defect_type=job.defect_type,
            report_url=report_url,
            severity=job.severity,
            expert_notes=job.expert_notes,
            name=job.name,
        )
        items.append(_to_report_item(resolved))
    return items


@router.get("/jobs/{job_id}", response_model=ReportItem)
async def get_job_for_review(
    job_id: str,
    user: Annotated[dict[str, object], Depends(_expert_or_admin)],
    job_repo: Annotated[PostgresJobRepository, Depends(get_job_repo)],
    storage: Annotated[S3StorageAdapter, Depends(get_storage)],
    vision_llm: Annotated[AnthropicAdapter, Depends(get_vision_llm)],
) -> ReportItem:
    job = await job_repo.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.assigned_expert_id and job.assigned_expert_id != str(user["sub"]):
        raise HTTPException(status_code=403, detail="Not the assigned expert")

    thumbnail_url: str | None = None
    if job.thumbnail_key:
        thumbnail_url = await storage.signed_url(job.thumbnail_key)

    report_url: str | None = None
    if job.report_key:
        report_url = await storage.signed_url(job.report_key)

    summary_for_expert = job.summary_expert or job.summary
    if (
        not job.summary_expert
        and job.summary
        and job.expert_language
        and job.expert_language != job.customer_language
    ):
        summary_for_expert = await vision_llm.translate(job.summary, job.expert_language)

    photo_urls = [await storage.signed_url(p.key) for p in job.photos]
    photo_thumb_urls = [await storage.signed_url(p.thumb_key) for p in job.photos if p.thumb_key]

    resolved = ResolvedJob(
        id=job.id,
        status=job.status.value,
        created_at=job.created_at,
        description=job.description,
        thumbnail_url=thumbnail_url,
        defect_type=job.defect_type,
        report_url=report_url,
        severity=job.severity,
        expert_notes=job.expert_notes,
        name=job.name,
        photo_urls=photo_urls,
        photo_thumb_urls=photo_thumb_urls or None,
        summary=summary_for_expert,
        verification_items=job.verification_items,
    )
    return _to_report_item(resolved)


@router.post("/jobs/{job_id}/approve")
async def approve_job(
    job_id: str,
    body: ApproveRequest,
    background_tasks: BackgroundTasks,
    user: Annotated[dict[str, object], Depends(_expert_or_admin)],
    job_repo: Annotated[PostgresJobRepository, Depends(get_job_repo)],
    user_repo: Annotated[PostgresUserRepository, Depends(get_user_repo)],
    storage: Annotated[S3StorageAdapter, Depends(get_storage)],
    renderer: Annotated[Xhtml2pdfAdapter, Depends(get_renderer)],
    email: Annotated[ResendAdapter, Depends(get_email)],
    vision_llm: Annotated[AnthropicAdapter, Depends(get_vision_llm)],
) -> dict[str, bool]:
    job = await job_repo.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.assigned_expert_id and job.assigned_expert_id != str(user["sub"]):
        raise HTTPException(status_code=403, detail="Not the assigned expert")
    if job.status != JobStatus.expert_review:
        raise HTTPException(status_code=409, detail="Job is not awaiting expert review")

    await job_repo.update_status(job_id, JobStatus.processing, expert_notes=body.expert_notes)

    generate = GenerateReport(
        storage=storage,
        job_repo=job_repo,
        user_repo=user_repo,
        renderer=renderer,
        email=email,
        vision_llm=vision_llm,
        fe_base_url=settings.fe_base_url,
    )
    background_tasks.add_task(generate.run, job_id)

    return {"ok": True}
