import contextlib
from typing import Any

from app.domain.job import JobStatus
from app.domain.ports.job_repo import JobRepository
from app.domain.ports.renderer import ReportRendererPort
from app.domain.ports.storage import StoragePort

from ..state import AssessmentState


def report_generator(
    storage: StoragePort,
    renderer: ReportRendererPort,
    job_repo: JobRepository,
) -> Any:  # LangGraph node callable
    async def _node(state: AssessmentState) -> dict[str, Any]:
        job = await job_repo.get(state["job_id"])
        if job is None:
            raise ValueError(f"Job {state['job_id']} not found")

        classification = state["defect_classification"]
        if classification is None:
            raise ValueError("defect_classification missing from state")

        photo_data: list[bytes] = []
        for photo in job.photos:
            with contextlib.suppress(Exception):
                photo_data.append(await storage.download(photo.key))

        pdf_bytes = await renderer.render(job, classification, photo_data)

        report_key = f"jobs/{job.id}/report.pdf"
        await storage.upload(report_key, pdf_bytes, "application/pdf")

        report_url = await storage.signed_url(report_key)
        severity = classification.severity

        await job_repo.update_status(
            job.id,
            JobStatus.complete,
            severity=severity,
            report_key=report_key,
            summary=classification.summary,
            summary_expert=classification.summary_expert,
        )

        return {
            "report_key": report_key,
            "report_url": report_url,
            "severity": severity,
        }

    return _node
