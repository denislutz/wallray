from app.application.list_jobs import ResolvedJob
from app.domain.job import JobStatus
from app.domain.ports.job_repo import JobRepository
from app.domain.ports.storage import StoragePort
from app.domain.ports.user_repo import UserRepository
from app.domain.ports.vision_llm import VisionLLMPort


class JobNotFoundError(Exception):
    pass


class GetReport:
    def __init__(
        self,
        storage: StoragePort,
        job_repo: JobRepository,
        user_repo: UserRepository,
        vision_llm: VisionLLMPort,
    ) -> None:
        self._storage = storage
        self._job_repo = job_repo
        self._user_repo = user_repo
        self._vision_llm = vision_llm

    async def execute(self, job_id: str, user_id: str) -> ResolvedJob:
        job = await self._job_repo.get(job_id)
        if job is None or job.user_id != user_id:
            raise JobNotFoundError(job_id)

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

        photo_urls = [await self._storage.signed_url(p.key) for p in job.photos]
        photo_thumb_urls = [
            await self._storage.signed_url(p.thumb_key) for p in job.photos if p.thumb_key
        ]

        return ResolvedJob(
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
            photo_urls=photo_urls,
            photo_thumb_urls=photo_thumb_urls or None,
            summary=job.summary,
            verification_items=job.verification_items,
        )
