from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.orm_models import JobRow
from app.domain.job import Job, JobStatus, Photo, PhotoRole


def _row_to_job(row: JobRow) -> Job:
    photos = [
        Photo(
            key=p["key"],
            content_type=p["content_type"],
            thumb_key=p.get("thumb_key"),
            role=PhotoRole(p["role"]) if p.get("role") else None,
        )
        for p in row.photos
    ]
    return Job(
        id=row.id,
        user_id=row.user_id,
        status=JobStatus(row.status),
        photos=photos,
        description=row.description,
        created_at=row.created_at,
        thumbnail_key=row.thumbnail_key,
        defect_type=row.defect_type,
        severity=row.severity,
        report_key=row.report_key,
        error=row.error,
        request_expert_review=row.request_expert_review,
        expert_notes=row.expert_notes,
        name=row.name,
        assigned_expert_id=row.assigned_expert_id,
        customer_language=row.customer_language,
        expert_language=row.expert_language,
        expert_report_key=row.expert_report_key,
        summary=row.summary,
        summary_expert=row.summary_expert,
        context_signals=row.context_signals,
        qa_history=row.qa_history,
        verification_items=row.verification_items,
        api_call_count=row.api_call_count,
    )


class PostgresJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, job: Job) -> None:
        row = JobRow(
            id=job.id,
            user_id=job.user_id,
            status=job.status.value,
            photos=[
                {
                    "key": p.key,
                    "content_type": p.content_type,
                    "thumb_key": p.thumb_key,
                    "role": p.role.value if p.role else None,
                }
                for p in job.photos
            ],
            description=job.description,
            thumbnail_key=job.thumbnail_key,
            defect_type=job.defect_type,
            severity=job.severity,
            report_key=job.report_key,
            error=job.error,
            request_expert_review=job.request_expert_review,
            expert_notes=job.expert_notes,
            name=job.name,
            assigned_expert_id=job.assigned_expert_id,
            customer_language=job.customer_language,
            context_signals=job.context_signals,
            qa_history=job.qa_history,
            verification_items=job.verification_items,
            api_call_count=job.api_call_count,
        )
        self._session.add(row)
        await self._session.commit()

    async def get(self, job_id: str) -> Job | None:
        result = await self._session.execute(select(JobRow).where(JobRow.id == job_id))
        row = result.scalar_one_or_none()
        return _row_to_job(row) if row is not None else None

    async def list_by_user(self, user_id: str) -> list[Job]:
        result = await self._session.execute(
            select(JobRow).where(JobRow.user_id == user_id).order_by(JobRow.created_at.desc())
        )
        return [_row_to_job(row) for row in result.scalars()]

    async def list_by_assigned_expert(self, expert_id: str, status: JobStatus) -> list[Job]:
        result = await self._session.execute(
            select(JobRow)
            .where(JobRow.assigned_expert_id == expert_id, JobRow.status == status.value)
            .order_by(JobRow.created_at.desc())
        )
        return [_row_to_job(row) for row in result.scalars()]

    async def list_all_by_assigned_expert(self, expert_id: str) -> list[Job]:
        result = await self._session.execute(
            select(JobRow)
            .where(JobRow.assigned_expert_id == expert_id)
            .order_by(JobRow.created_at.desc())
        )
        return [_row_to_job(row) for row in result.scalars()]

    async def update_status(self, job_id: str, status: JobStatus, **fields: Any) -> None:
        await self._session.execute(
            update(JobRow).where(JobRow.id == job_id).values(status=status.value, **fields)
        )
        await self._session.commit()
