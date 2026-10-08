from typing import Any

from app.domain.job import JobStatus
from app.domain.ports.job_repo import JobRepository
from app.domain.ports.vision_llm import VisionLLMPort

from ..call_budget import guard_call_budget
from ..state import AssessmentState


def ai_assessment(
    vision_llm: VisionLLMPort, job_repo: JobRepository
) -> Any:  # LangGraph node callable
    async def _node(state: AssessmentState) -> dict[str, Any]:
        await guard_call_budget(job_repo, state["job_id"], state["api_call_count"])

        prior = state.get("defect_classification")
        classification = await vision_llm.assess(
            state["photo_keys"],
            state["context_signals"],
            prior_summary=prior.summary if prior else None,
            customer_language=state["customer_language"],
        )

        await job_repo.update_status(
            state["job_id"],
            JobStatus.processing,
            defect_type=classification.defect_type,
            severity=classification.severity,
            summary=classification.summary,
            verification_items=classification.verification_items,
            api_call_count=state["api_call_count"] + 1,
        )
        return {
            "defect_classification": classification,
            "confidence": classification.confidence,
            "verification_items": classification.verification_items or [],
            "severity": classification.severity,
            "api_call_count": state["api_call_count"] + 1,
        }

    return _node
