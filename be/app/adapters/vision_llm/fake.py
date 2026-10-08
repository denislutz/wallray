from __future__ import annotations

from typing import Any

from app.domain.job import DefectClassification, IntakeResult, PhotoRole

_ROLE_CYCLE = (PhotoRole.close_up, PhotoRole.context, PhotoRole.repeat_location)

_FAKE_DEFECT_TYPE = "crack"
_FAKE_SEVERITY = "medium"
_FAKE_SUMMARY = "Fake E2E assessment: hairline crack near a window corner, likely thermal movement."
_FAKE_VERIFICATION_ITEM = {"text": "How old is the building?", "kind": "customer_question"}


class FakeVisionLLMAdapter:
    """Deterministic, instant stand-in for AnthropicAdapter.

    Only ever selected by `api/deps.py::get_vision_llm` when `settings.debug` is true AND the
    request carries `X-E2E-Fake-Ai` — i.e. only for Playwright-originated requests, never for a
    human's manual QA session on the same environment. Keeps the default E2E suite free of real
    model latency/cost/nondeterminism while still exercising the real clarification-loop state
    machine: the first `assess()` call for a given job raises one customer question (driving the
    real `await_customer_answers` pipeline node to pause), the second returns a final answer.
    """

    def __init__(self) -> None:
        self._assess_calls: dict[tuple[str, ...], int] = {}

    async def validate_intake(self, photo_keys: list[str]) -> IntakeResult:
        photo_roles = {key: _ROLE_CYCLE[i % len(_ROLE_CYCLE)] for i, key in enumerate(photo_keys)}
        return IntakeResult(accepted=True, rejection_reason=None, photo_roles=photo_roles)

    async def translate(self, text: str, target_language: str) -> str:
        return text

    async def assess(
        self,
        photo_keys: list[str],
        context_signals: dict[str, Any],
        prior_summary: str | None = None,
        expert_notes: str | None = None,
        customer_language: str = "en",
        expert_language: str | None = None,
    ) -> DefectClassification:
        if expert_notes is not None:
            return DefectClassification(
                defect_type=_FAKE_DEFECT_TYPE,
                severity=_FAKE_SEVERITY,
                summary=_FAKE_SUMMARY,
                summary_expert=_FAKE_SUMMARY
                if expert_language and expert_language != customer_language
                else None,
                expert_note_localized=expert_notes or None,
            )

        key = tuple(photo_keys)
        call_number = self._assess_calls.get(key, 0) + 1
        self._assess_calls[key] = call_number

        verification_items = [_FAKE_VERIFICATION_ITEM] if call_number == 1 else []
        return DefectClassification(
            defect_type=_FAKE_DEFECT_TYPE,
            severity=_FAKE_SEVERITY,
            summary=_FAKE_SUMMARY,
            confidence=0.9,
            verification_items=verification_items,
        )
