from typing import Any

from app.domain.job import JobStatus
from app.domain.ports.job_repo import JobRepository

from ..state import AssessmentState


def await_customer_answers(job_repo: JobRepository) -> Any:  # LangGraph node callable
    """Pauses the job for a customer reply-or-accept round.

    No LLM call — this node only flips status. The graph run ends here; resuming (accept or
    reply) happens outside this graph invocation, via `POST /jobs/{id}/respond`
    (`RespondToJob`), since the customer may take minutes or days to respond and this process
    may not even be the one that resumes it. The Job row (not a LangGraph checkpoint) is the
    durable state store across that gap — see AI_ASSESSMENT_REWORK.md's `await_customer_answers`
    section.
    """

    async def _node(state: AssessmentState) -> dict[str, Any]:
        await job_repo.update_status(state["job_id"], JobStatus.awaiting_customer_input)
        return {}

    return _node
