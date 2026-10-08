from typing import Any, Protocol

from app.domain.job import DefectClassification, IntakeResult


class VisionLLMPort(Protocol):
    async def validate_intake(self, photo_keys: list[str]) -> IntakeResult: ...

    async def translate(self, text: str, target_language: str) -> str: ...

    async def assess(
        self,
        photo_keys: list[str],
        context_signals: dict[str, Any],
        prior_summary: str | None = None,
        expert_notes: str | None = None,
        customer_language: str = "en",
        expert_language: str | None = None,
    ) -> DefectClassification: ...
