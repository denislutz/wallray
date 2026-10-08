from typing import Protocol

from app.domain.job import DefectClassification, Job


class ReportRendererPort(Protocol):
    async def render(
        self,
        job: Job,
        classification: DefectClassification,
        photo_data: list[bytes],
        expert_notes: str | None = None,
        summary_override: str | None = None,
        locale: str | None = None,
    ) -> bytes: ...
