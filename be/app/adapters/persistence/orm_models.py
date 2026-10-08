import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid, false, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.db import Base


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    report_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    role: Mapped[str] = mapped_column(String, nullable=False, server_default="customer")
    preferred_language: Mapped[str] = mapped_column(String, nullable=False, server_default="en")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    terms_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class OtpTokenRow(Base):
    __tablename__ = "otp_tokens"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String, nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class JobRow(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    user_id: Mapped[str] = mapped_column(Uuid(as_uuid=False), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    photos: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_key: Mapped[str | None] = mapped_column(String, nullable=True)
    defect_type: Mapped[str | None] = mapped_column(String, nullable=True)
    severity: Mapped[str | None] = mapped_column(String, nullable=True)
    report_key: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    assigned_expert_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    request_expert_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=false()
    )
    expert_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_language: Mapped[str] = mapped_column(String, nullable=False, server_default="en")
    expert_language: Mapped[str | None] = mapped_column(String, nullable=True)
    expert_report_key: Mapped[str | None] = mapped_column(String, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_expert: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_signals: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    qa_history: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    verification_items: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    api_call_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
