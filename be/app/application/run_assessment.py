import logging

from app.application.pipeline import graph as pipeline_graph
from app.application.pipeline.state import AssessmentState
from app.domain.job import JobStatus
from app.domain.ports.email import EmailPort
from app.domain.ports.job_repo import JobRepository
from app.domain.ports.renderer import ReportRendererPort
from app.domain.ports.storage import StoragePort
from app.domain.ports.user_repo import UserRepository
from app.domain.ports.vision_llm import VisionLLMPort

logger = logging.getLogger(__name__)


class RunAssessment:
    def __init__(
        self,
        storage: StoragePort,
        job_repo: JobRepository,
        user_repo: UserRepository,
        vision_llm: VisionLLMPort,
        renderer: ReportRendererPort,
        email: EmailPort,
        fe_base_url: str,
    ) -> None:
        self._storage = storage
        self._job_repo = job_repo
        self._user_repo = user_repo
        self._vision_llm = vision_llm
        self._renderer = renderer
        self._email = email
        self._fe_base_url = fe_base_url

    async def run(self, job_id: str, user_id: str) -> None:
        job = await self._job_repo.get(job_id)
        if job is None or job.user_id != user_id:
            logger.error("Job %s not found for user %s", job_id, user_id)
            return

        initial: AssessmentState = AssessmentState(
            job_id=job_id,
            user_id=user_id,
            photo_keys=[p.key for p in job.photos],
            description=job.description,
            request_expert_review=False,
            assigned_expert_id=None,
            validation_passed=False,
            validation_errors=[],
            photo_roles={},
            context_signals={},
            defect_classification=None,
            severity=None,
            report_key=None,
            report_url=None,
            expert_notes=None,
            customer_language=job.customer_language,
            expert_language=None,
            confidence=None,
            verification_items=[],
            qa_history=job.qa_history or [],
            loop_count=0,
            api_call_count=job.api_call_count,
        )

        graph = pipeline_graph.build(
            self._storage,
            self._job_repo,
            self._user_repo,
            self._vision_llm,
            self._renderer,
            self._email,
            self._fe_base_url,
        )

        try:
            final_state: AssessmentState = await graph.ainvoke(initial)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Pipeline failed for job %s", job_id)
            await self._job_repo.update_status(job_id, JobStatus.failed, error=str(exc))
            return

        if not final_state["validation_passed"]:
            error_msg = "; ".join(final_state["validation_errors"]) or "Photo validation failed"
            await self._job_repo.update_status(job_id, JobStatus.failed, error=error_msg)
            return

        if not final_state["report_key"]:
            # Paused at await_customer_answers (JobStatus.awaiting_customer_input) — nothing
            # further to do until the customer responds via POST /jobs/{id}/respond.
            return

        # report_generator ran — counts as a completed report regardless of whether expert
        # review was additionally requested (GenerateReport re-renders later but doesn't
        # produce a second billable report).
        await self._user_repo.increment_count(user_id)
        # Customer "report ready" email disabled for now — re-enable in the future.
        logger.info("Report ready email disabled — skipping for job %s", job_id)
        # user = await self._user_repo.get(user_id)
        # if user and user.email:
        #     report_url = final_state["report_url"] or ""
        #     app_report_url = f"{self._fe_base_url}/reports/{job_id}"
        #     with contextlib.suppress(Exception):
        #         await self._email.send_report(
        #             user.email, job_id, report_url, app_report_url, locale=job.customer_language
        #         )
