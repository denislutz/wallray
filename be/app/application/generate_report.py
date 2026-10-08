import contextlib
import logging

from app.application.pipeline.call_budget import CallBudgetExceededError, guard_call_budget
from app.domain.job import JobStatus
from app.domain.ports.email import EmailPort
from app.domain.ports.job_repo import JobRepository
from app.domain.ports.renderer import ReportRendererPort
from app.domain.ports.storage import StoragePort
from app.domain.ports.user_repo import UserRepository
from app.domain.ports.vision_llm import VisionLLMPort

logger = logging.getLogger(__name__)


class GenerateReport:
    def __init__(
        self,
        storage: StoragePort,
        job_repo: JobRepository,
        user_repo: UserRepository,
        renderer: ReportRendererPort,
        email: EmailPort,
        vision_llm: VisionLLMPort,
        fe_base_url: str,
    ) -> None:
        self._storage = storage
        self._job_repo = job_repo
        self._user_repo = user_repo
        self._renderer = renderer
        self._email = email
        self._vision_llm = vision_llm
        self._fe_base_url = fe_base_url

    async def run(self, job_id: str) -> None:
        job = await self._job_repo.get(job_id)
        if job is None:
            logger.error("GenerateReport: job %s not found", job_id)
            return

        customer_language = job.customer_language
        expert_language = job.expert_language or "en"

        try:
            await guard_call_budget(self._job_repo, job_id, job.api_call_count)
        except CallBudgetExceededError:
            return

        try:
            final_classification = await self._vision_llm.assess(
                [p.key for p in job.photos],
                job.context_signals or {},
                prior_summary=job.summary,
                expert_notes=job.expert_notes,
                customer_language=customer_language,
                expert_language=expert_language,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("GenerateReport: synthesis failed for job %s", job_id)
            await self._job_repo.update_status(job_id, JobStatus.failed, error=str(exc))
            return

        photo_data: list[bytes] = []
        for photo in job.photos:
            with contextlib.suppress(Exception):
                photo_data.append(await self._storage.download(photo.key))

        try:
            customer_pdf = await self._renderer.render(
                job, final_classification, photo_data, expert_notes=job.expert_notes
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("GenerateReport: render failed for job %s", job_id)
            await self._job_repo.update_status(job_id, JobStatus.failed, error=str(exc))
            return

        report_key = f"jobs/{job.id}/report.pdf"
        await self._storage.upload(report_key, customer_pdf, "application/pdf")

        expert_report_key: str | None = None
        if final_classification.summary_expert:
            try:
                expert_pdf = await self._renderer.render(
                    job,
                    final_classification,
                    photo_data,
                    expert_notes=job.expert_notes,
                    summary_override=final_classification.summary_expert,
                    locale=expert_language,
                )
                expert_report_key = f"jobs/{job.id}/report_expert.pdf"
                await self._storage.upload(expert_report_key, expert_pdf, "application/pdf")
            except Exception:  # noqa: BLE001
                logger.exception("GenerateReport: expert PDF render failed for job %s", job_id)

        await self._job_repo.update_status(
            job.id,
            JobStatus.complete,
            report_key=report_key,
            expert_report_key=expert_report_key,
            summary=final_classification.summary,
            summary_expert=final_classification.summary_expert,
            api_call_count=job.api_call_count + 1,
        )
        # No increment_count here — the AI-only report already counted it (RunAssessment /
        # RespondToJob); this is a re-render of the same job's report, not a second one.

        # Customer + expert "report ready" emails disabled for now — re-enable in the future.
        logger.info("Report ready emails disabled — skipping for job %s", job_id)
        # app_report_url = f"{self._fe_base_url}/reports/{job.id}"
        # user = await self._user_repo.get(job.user_id)
        # if user and user.email:
        #     customer_url = await self._storage.signed_url(report_key)
        #     with contextlib.suppress(Exception):
        #         await self._email.send_report(
        #             user.email, job_id, customer_url, app_report_url, locale=customer_language
        #         )
        #
        # if job.assigned_expert_id:
        #     expert = await self._user_repo.get(job.assigned_expert_id)
        #     if expert and expert.email:
        #         expert_url_key = expert_report_key or report_key
        #         expert_url = await self._storage.signed_url(expert_url_key)
        #         with contextlib.suppress(Exception):
        #             await self._email.send_report(
        #                 expert.email, job_id, expert_url, app_report_url, locale=expert_language
        #             )
