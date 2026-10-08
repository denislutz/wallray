from app.core.config import settings
from app.domain.job import JobStatus
from app.domain.ports.job_repo import JobRepository

_LIMIT_REASON = "api_call_limit_exceeded"


class CallBudgetExceededError(Exception):
    def __init__(self, job_id: str) -> None:
        super().__init__(_LIMIT_REASON)
        self.job_id = job_id


async def guard_call_budget(job_repo: JobRepository, job_id: str, api_call_count: int) -> None:
    """Raise (and fail the job) if this job is already at the Anthropic call ceiling.

    Independent of the clarification loop's own bookkeeping (`loop_count <
    customer_after_questions`) — a design bound assumes the branch logic is correct, this is a
    hard stop that doesn't. See AI_ASSESSMENT_REWORK.md "Anthropic API call cap".
    """
    if api_call_count >= settings.anthropic_max_calls_per_job:
        await job_repo.update_status(job_id, JobStatus.failed, error=_LIMIT_REASON)
        raise CallBudgetExceededError(job_id)
