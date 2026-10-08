from typing import Any, TypedDict

from app.domain.job import DefectClassification, PhotoRole


class AssessmentState(TypedDict):
    job_id: str
    user_id: str
    photo_keys: list[str]
    description: str | None
    request_expert_review: bool
    assigned_expert_id: str | None
    validation_passed: bool
    validation_errors: list[str]
    photo_roles: dict[str, PhotoRole]
    context_signals: dict[str, Any]
    defect_classification: DefectClassification | None
    severity: str | None
    report_key: str | None
    report_url: str | None
    expert_notes: str | None
    customer_language: str
    expert_language: str | None
    confidence: float | None
    verification_items: list[dict[str, str]]
    qa_history: list[dict[str, Any]]
    loop_count: int
    api_call_count: int
