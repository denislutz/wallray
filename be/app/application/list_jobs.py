from dataclasses import dataclass
from datetime import datetime

from app.domain.job import JobStatus
from app.domain.ports.job_repo import JobRepository
from app.domain.ports.storage import StoragePort
from app.domain.ports.user_repo import UserRepository


@dataclass
class ResolvedJob:
    id: str
    status: str
    created_at: datetime
    description: str | None
    thumbnail_url: str | None
    defect_type: str | None
    report_url: str | None
    severity: str | None
    expert_notes: str | None = None
    name: str | None = None
    summary: str | None = None
    request_expert_review: bool = False
    assigned_expert_email: str | None = None
    photo_urls: list[str] | None = None
    photo_thumb_urls: list[str] | None = None
    verification_items: list[dict[str, str]] | None = None


class ListJobs:
    def __init__(
        self, storage: StoragePort, job_repo: JobRepository, user_repo: UserRepository
    ) -> None:
        self._storage = storage
        self._job_repo = job_repo
        self._user_repo = user_repo

    async def execute(self, user_id: str) -> list[ResolvedJob]:
        jobs = await self._job_repo.list_by_user(user_id)
        items: list[ResolvedJob] = []

        for job in jobs:
            thumbnail_url: str | None = None
            if job.thumbnail_key:
                thumbnail_url = await self._storage.signed_url(job.thumbnail_key)

            report_url: str | None = None
            if job.status == JobStatus.complete and job.report_key:
                report_url = await self._storage.signed_url(job.report_key)

            assigned_expert_email: str | None = None
            if job.assigned_expert_id:
                expert = await self._user_repo.get(job.assigned_expert_id)
                if expert:
                    assigned_expert_email = expert.email

            items.append(
                ResolvedJob(
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
                    request_expert_review=job.request_expert_review,
                    assigned_expert_email=assigned_expert_email,
                )
            )

        return items
