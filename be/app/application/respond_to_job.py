import logging

from app.application.pipeline import graph as pipeline_graph
from app.application.pipeline.nodes.expert_notifier import expert_notifier
from app.application.pipeline.nodes.report_generator import report_generator
from app.application.pipeline.state import AssessmentState
from app.domain.job import DefectClassification, Job, JobStatus
from app.domain.ports.email import EmailPort
from app.domain.ports.job_repo import JobRepository
from app.domain.ports.renderer import ReportRendererPort
from app.domain.ports.storage import StoragePort
from app.domain.ports.user_repo import UserRepository
from app.domain.ports.vision_llm import VisionLLMPort

logger = logging.getLogger(__name__)


def _base_state(job: Job) -> AssessmentState:
    return AssessmentState(
        job_id=job.id,
        user_id=job.user_id,
        photo_keys=[p.key for p in job.photos],
        description=job.description,
        request_expert_review=job.request_expert_review,
        assigned_expert_id=job.assigned_expert_id,
        validation_passed=True,
        validation_errors=[],
        photo_roles={},
        context_signals=job.context_signals or {},
        defect_classification=DefectClassification(
            defect_type=job.defect_type or "unknown",
            severity=job.severity or "unknown",
            summary=job.summary,
            verification_items=job.verification_items,
        )
        if job.defect_type
        else None,
        severity=job.severity,
        report_key=None,
        report_url=None,
        expert_notes=job.expert_notes,
        customer_language=job.customer_language,
        expert_language=job.expert_language,
        confidence=None,
        verification_items=job.verification_items or [],
        qa_history=job.qa_history or [],
        loop_count=len(job.qa_history or []),
        api_call_count=job.api_call_count,
    )


class RespondToJob:
    """Handles the one clarification-loop round (`await_customer_answers`) — accept or reply.

    Runs outside the pipeline's own graph invocation, since the customer's response may arrive
    in a different process, possibly days later; the Job row (not a LangGraph checkpoint) is
    what carries state across that gap. See AI_ASSESSMENT_REWORK.md's `await_customer_answers`.
    """

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

    async def run(
        self,
        job_id: str,
        user_id: str,
        reply: str | None,
        request_expert_review: bool = False,
        assigned_expert_id: str | None = None,
    ) -> None:
        job = await self._job_repo.get(job_id)
        if job is None or job.user_id != user_id:
            logger.error("RespondToJob: job %s not found for user %s", job_id, user_id)
            return

        if request_expert_review:
            await self._request_expert(job, assigned_expert_id)
        elif reply and reply.strip():
            await self._reply(job, reply.strip())
        else:
            await self._accept(job)

    async def _accept(self, job: Job) -> None:
        # No LLM call — the last ai_assessment output is rendered as-is.
        state = _base_state(job)

        render = report_generator(self._storage, self._renderer, self._job_repo)
        state.update(await render(state))

        await self._user_repo.increment_count(job.user_id)

    async def _request_expert(self, job: Job, assigned_expert_id: str | None) -> None:
        # No AI-only render on this path — the first PDF is the one generate_report.py
        # produces once the expert submits notes.
        await self._job_repo.update_status(
            job.id,
            JobStatus.processing,
            request_expert_review=True,
            assigned_expert_id=assigned_expert_id,
        )

        state = _base_state(job)
        state["request_expert_review"] = True
        state["assigned_expert_id"] = assigned_expert_id

        notify = expert_notifier(
            self._job_repo, self._user_repo, self._email, self._fe_base_url, self._vision_llm
        )
        await notify(state)

        await self._user_repo.increment_count(job.user_id)

    async def _reply(self, job: Job, reply: str) -> None:
        round_num = len(job.qa_history or [])
        qa_history = [*(job.qa_history or []), {"round": round_num, "customer_reply": reply}]
        context_signals = {
            **(job.context_signals or {}),
            f"customer_reply_round_{round_num}": reply,
        }

        await self._job_repo.update_status(
            job.id, JobStatus.processing, context_signals=context_signals, qa_history=qa_history
        )

        initial = _base_state(job)
        initial["context_signals"] = context_signals
        initial["qa_history"] = qa_history
        initial["loop_count"] = len(qa_history)

        graph = pipeline_graph.build_resume(
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
            logger.exception("RespondToJob: resume pipeline failed for job %s", job.id)
            await self._job_repo.update_status(job.id, JobStatus.failed, error=str(exc))
            return

        if final_state["report_key"]:
            await self._user_repo.increment_count(job.user_id)
        # else: looped back to another await_customer_answers round — nothing further to do.
