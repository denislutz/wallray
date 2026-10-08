from typing import Any

from ..state import AssessmentState


def context_intake() -> Any:  # LangGraph node callable
    async def _node(state: AssessmentState) -> dict[str, Any]:
        context_signals = {**state.get("context_signals", {}), "description": state["description"]}
        return {"context_signals": context_signals}

    return _node
