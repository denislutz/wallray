from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class ReportStatus(StrEnum):
    pending = "pending"
    processing = "processing"
    awaiting_customer_input = "awaiting_customer_input"
    expert_review = "expert_review"
    complete = "complete"
    failed = "failed"


class VerificationItem(BaseModel):
    text: str
    kind: str


class ReportItem(BaseModel):
    """Single shape for both GET /jobs (list) and GET /report/{id} (detail)."""

    id: str
    status: ReportStatus
    created_at: datetime
    description: str | None = None
    name: str | None = None
    thumbnail_url: str | None = None
    defect_type: str | None = None
    report_url: str | None = None
    severity: str | None = None
    expert_notes: str | None = None
    summary: str | None = None
    request_expert_review: bool = False
    assigned_expert_email: str | None = None
    photo_urls: list[str] | None = None
    photo_thumb_urls: list[str] | None = None
    verification_items: list[VerificationItem] | None = None


class MeResponse(BaseModel):
    role: str
    email: str
    preferred_language: str


class LanguageUpdate(BaseModel):
    language: str


class ExpertItem(BaseModel):
    id: str
    email: str


class UploadResponse(BaseModel):
    job_id: str


class ApproveRequest(BaseModel):
    expert_notes: str | None = None


class RespondRequest(BaseModel):
    reply: str | None = None
    request_expert_review: bool = False
    assigned_expert_id: str | None = None
