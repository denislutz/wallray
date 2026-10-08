import contextlib
import logging
from typing import Any

from app.domain.job import JobStatus
from app.domain.ports.email import EmailPort
from app.domain.ports.job_repo import JobRepository
from app.domain.ports.user_repo import UserRepository
from app.domain.ports.vision_llm import VisionLLMPort

from ..state import AssessmentState

logger = logging.getLogger(__name__)


def expert_notifier(
    job_repo: JobRepository,
    user_repo: UserRepository,
    email: EmailPort,
    app_url: str,
    vision_llm: VisionLLMPort,
) -> Any:  # LangGraph node callable
    async def _node(state: AssessmentState) -> dict[str, Any]:
        assigned_id = state["assigned_expert_id"]
        expert = await user_repo.get(assigned_id) if assigned_id else None
        expert_lang = expert.preferred_language if expert else "en"
        expert_email = expert.email if expert else ""

        classification = state.get("defect_classification")
        notes_for_expert = (classification.summary if classification else "") or ""
        if notes_for_expert and expert_lang != state["customer_language"]:
            notes_for_expert = await vision_llm.translate(notes_for_expert, expert_lang)

        await job_repo.update_status(
            state["job_id"],
            JobStatus.expert_review,
            expert_language=expert_lang,
        )
        review_url = f"{app_url}/expert/review/{state['job_id']}"
        with contextlib.suppress(Exception):
            await email.send_expert_review_request(
                to=expert_email,
                job_id=state["job_id"],
                review_url=review_url,
                defect_type=classification.defect_type if classification else "unknown",
                severity=classification.severity if classification else "unknown",
                assessment_summary=notes_for_expert or None,
                locale=expert_lang,
            )
        logger.info(
            "Expert notifier complete for job %s (expert=%s)", state["job_id"], expert_email
        )
        return {"expert_language": expert_lang}

    return _node
