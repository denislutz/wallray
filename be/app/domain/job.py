from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class JobStatus(StrEnum):
    pending = "pending"
    processing = "processing"
    awaiting_customer_input = "awaiting_customer_input"
    expert_review = "expert_review"
    complete = "complete"
    failed = "failed"


class PhotoRole(StrEnum):
    close_up = "close_up"
    context = "context"
    repeat_location = "repeat_location"


@dataclass(frozen=True)
class Photo:
    key: str
    content_type: str
    thumb_key: str | None = None
    role: PhotoRole | None = None


@dataclass
class DefectClassification:
    """Output of every `assess()` call — the same method whether this is the first pass, a
    customer-reply rerun, or a post-expert-review regeneration."""

    defect_type: str
    severity: str
    summary: str | None = None
    summary_expert: str | None = None
    expert_note_localized: str | None = None
    confidence: float | None = None
    verification_items: list[dict[str, str]] | None = None


@dataclass
class IntakeResult:
    accepted: bool
    rejection_reason: str | None
    photo_roles: dict[str, PhotoRole]


@dataclass
class Job:
    id: str
    user_id: str
    status: JobStatus
    photos: list[Photo]
    description: str | None
    created_at: datetime
    thumbnail_key: str | None = None
    defect_type: str | None = None
    severity: str | None = None
    report_key: str | None = None
    error: str | None = None
    request_expert_review: bool = False
    expert_notes: str | None = None
    name: str | None = None
    assigned_expert_id: str | None = None
    customer_language: str = "en"
    expert_language: str | None = None
    expert_report_key: str | None = None
    summary: str | None = None
    summary_expert: str | None = None
    context_signals: dict[str, Any] | None = None
    qa_history: list[dict[str, Any]] | None = None
    verification_items: list[dict[str, str]] | None = None
    api_call_count: int = 0
