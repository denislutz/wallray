from typing import Any

from langgraph.graph import END, StateGraph

from app.core.config import settings
from app.domain.ports.email import EmailPort
from app.domain.ports.job_repo import JobRepository
from app.domain.ports.renderer import ReportRendererPort
from app.domain.ports.storage import StoragePort
from app.domain.ports.user_repo import UserRepository
from app.domain.ports.vision_llm import VisionLLMPort

from .nodes.ai_assessment import ai_assessment
from .nodes.await_customer_answers import await_customer_answers
from .nodes.context_intake import context_intake
from .nodes.intake_gate import intake_gate
from .nodes.report_generator import report_generator
from .state import AssessmentState


def _loop_branch(state: AssessmentState) -> str:
    loop_count = len(state.get("qa_history", []))
    if loop_count < settings.customer_after_questions:
        return "await_customer_answers"
    return "report_generator"


def _wire_downstream_of_assessment(
    g: StateGraph[AssessmentState],
    storage: StoragePort,
    job_repo: JobRepository,
    user_repo: UserRepository,
    vision_llm: VisionLLMPort,
    renderer: ReportRendererPort,
    email: EmailPort,
    app_url: str,
) -> None:
    g.add_node("ai_assessment", ai_assessment(vision_llm, job_repo))
    g.add_node("await_customer_answers", await_customer_answers(job_repo))
    g.add_node("report_generator", report_generator(storage, renderer, job_repo))

    g.add_conditional_edges("ai_assessment", _loop_branch)
    g.add_edge("await_customer_answers", END)
    g.add_edge("report_generator", END)


def build(
    storage: StoragePort,
    job_repo: JobRepository,
    user_repo: UserRepository,
    vision_llm: VisionLLMPort,
    renderer: ReportRendererPort,
    email: EmailPort,
    app_url: str,
) -> Any:  # langgraph.CompiledStateGraph — no public type alias
    g: StateGraph[AssessmentState] = StateGraph(AssessmentState)

    g.add_node("intake_gate", intake_gate(storage, job_repo, vision_llm))
    g.add_node("context_intake", context_intake())
    _wire_downstream_of_assessment(
        g, storage, job_repo, user_repo, vision_llm, renderer, email, app_url
    )

    g.set_entry_point("intake_gate")
    g.add_conditional_edges(
        "intake_gate",
        lambda state: "context_intake" if state["validation_passed"] else END,
    )
    g.add_edge("context_intake", "ai_assessment")

    return g.compile()


def build_resume(
    storage: StoragePort,
    job_repo: JobRepository,
    user_repo: UserRepository,
    vision_llm: VisionLLMPort,
    renderer: ReportRendererPort,
    email: EmailPort,
    app_url: str,
) -> Any:  # langgraph.CompiledStateGraph — no public type alias
    """Entry point for the clarification-loop reply path (`RespondToJob`).

    Same downstream shape as `build()`'s post-intake portion, entered directly at
    `ai_assessment` — intake and context assembly only need to happen once per job, and the
    customer's reply may arrive in a different process than the one that ran them, so this
    graph reconstructs from the persisted Job row rather than resuming the first graph in place.
    """
    g: StateGraph[AssessmentState] = StateGraph(AssessmentState)
    _wire_downstream_of_assessment(
        g, storage, job_repo, user_repo, vision_llm, renderer, email, app_url
    )
    g.set_entry_point("ai_assessment")
    return g.compile()
