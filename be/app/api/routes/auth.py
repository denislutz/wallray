import contextlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import uuid4

import bcrypt
import httpx
import resend
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.email.resend import ResendAdapter
from app.adapters.persistence.orm_models import OtpTokenRow, UserRow
from app.api.deps import get_email
from app.core.config import settings
from app.core.db import get_session
from app.core.rate_limit import limiter
from app.domain.user import UserRole

router = APIRouter(prefix="/auth", tags=["auth"])

_OTP_EXPIRY_MINUTES = 5

_TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

# Honored only when settings.debug is true (never prod) — global-setup.ts mints session cookies
# via a raw fetch with no browser, so it can never produce a real Turnstile token. The one spec
# that drives the actual sign-in UI (auth.spec.ts) goes through the real widget + verification
# instead of this header.
_E2E_SKIP_TURNSTILE_HEADER = "x-e2e-skip-turnstile"

# Transient plaintext capture for E2E — populated only when settings.debug is true, read by
# GET /auth/otp/debug so Playwright can drive the real sign-in UI without an email inbox.
_last_otp_codes: dict[str, str] = {}


def _utcnow() -> datetime:
    return datetime.now(UTC)


class _SendRequest(BaseModel):
    email: EmailStr
    terms_accepted: bool
    turnstile_token: str = ""


class _VerifyRequest(BaseModel):
    email: EmailStr
    code: str


class VerifyResponse(BaseModel):
    id: str
    email: str
    name: str | None = None


async def _verify_turnstile(token: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as http_client:
            resp = await http_client.post(
                _TURNSTILE_VERIFY_URL,
                data={"secret": settings.turnstile_secret_key, "response": token},
            )
        result: dict[str, object] = resp.json()
        return bool(result.get("success"))
    except Exception as exc:
        logging.exception("Turnstile verification request failed: %s", exc)
        return False


@router.post("/otp/send", status_code=200)
@limiter.limit("3/hour;10/day")
async def send_otp(
    request: Request,
    body: _SendRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, str]:
    if not body.terms_accepted:
        raise HTTPException(status_code=400, detail="Terms must be accepted")

    skip_turnstile = settings.debug and request.headers.get(_E2E_SKIP_TURNSTILE_HEADER) == "1"
    if (
        settings.turnstile_secret_key
        and not skip_turnstile
        and not await _verify_turnstile(body.turnstile_token)
    ):
        raise HTTPException(status_code=400, detail="Captcha verification failed")

    code = f"{secrets.randbelow(1_000_000):06d}"
    code_hash = bcrypt.hashpw(code.encode(), bcrypt.gensalt()).decode()
    expires_at = _utcnow() + timedelta(minutes=_OTP_EXPIRY_MINUTES)

    await session.execute(delete(OtpTokenRow).where(OtpTokenRow.email == str(body.email)))
    session.add(OtpTokenRow(email=str(body.email), code_hash=code_hash, expires_at=expires_at))
    await session.commit()

    if settings.debug:
        _last_otp_codes[str(body.email)] = code

    if settings.resend_api_key:
        try:
            resend.api_key = settings.resend_api_key
            resend.Emails.send(
                {
                    "from": "noreply@example.com",
                    "to": [str(body.email)],
                    "subject": "Your WallRay sign-in code",
                    "html": (
                        f"<p>Your sign-in code is: <strong>{code}</strong></p>"
                        f"<p>It expires in {_OTP_EXPIRY_MINUTES} minutes.</p>"
                        f"<p><a href='{settings.marketing_base_url}/legal'>Privacy Policy &amp; Disclaimer</a></p>"
                    ),
                }
            )
        except Exception as exc:
            logging.exception("Resend send failed: %s", exc)
            print(f"[auth] Resend error: {exc}", flush=True)

    return {"status": "ok"}


@router.post("/otp/verify", response_model=VerifyResponse)
async def verify_otp(
    body: _VerifyRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    email: Annotated[ResendAdapter, Depends(get_email)],
) -> VerifyResponse:
    result = await session.execute(select(OtpTokenRow).where(OtpTokenRow.email == str(body.email)))
    token = result.scalar_one_or_none()

    def _is_expired(t: OtpTokenRow) -> bool:
        expires_at = (
            t.expires_at.replace(tzinfo=UTC) if t.expires_at.tzinfo is None else t.expires_at
        )
        return expires_at < _utcnow()

    if (
        token is None
        or _is_expired(token)
        or not bcrypt.checkpw(body.code.encode(), token.code_hash.encode())
    ):
        raise HTTPException(status_code=401, detail="Invalid or expired code")

    await session.execute(delete(OtpTokenRow).where(OtpTokenRow.id == token.id))

    user_result = await session.execute(select(UserRow).where(UserRow.email == str(body.email)))
    user = user_result.scalar_one_or_none()
    is_new_user = user is None
    if user is None:
        email_lower = str(body.email).lower()
        if email_lower in settings.admin_emails_set:
            role = UserRole.admin
        elif email_lower in settings.expert_review_emails_set:
            role = UserRole.expert_review
        else:
            role = UserRole.customer
        user = UserRow(
            id=str(uuid4()),
            email=str(body.email),
            role=role.value,
            terms_accepted_at=_utcnow(),
        )
        session.add(user)

    await session.commit()
    await session.refresh(user)

    if is_new_user:
        if settings.debug:
            logging.info(
                "Skipping new-user notification for %s — settings.debug is true "
                "(local/test environment)",
                user.email,
            )
        else:
            with contextlib.suppress(Exception):
                await email.send_new_user_notification(
                    to=settings.new_user_notification_email,
                    user_email=user.email,
                    role=user.role,
                )

    return VerifyResponse(id=str(user.id), email=user.email, name=user.name)


@router.get("/otp/debug")
async def debug_otp(email: str) -> dict[str, str]:
    """E2E-only: returns the last plaintext OTP code sent to `email`.

    A 404 no-op whenever `settings.debug` is false — i.e. always in prod, regardless of who
    calls it. Only ever used by Playwright's global-setup to drive the real sign-in UI without
    an email inbox; the code is never persisted anywhere else (only bcrypt-hashed in Postgres).
    """
    if not settings.debug:
        raise HTTPException(status_code=404)
    code = _last_otp_codes.get(email)
    if code is None:
        raise HTTPException(status_code=404, detail="No OTP sent for this email")
    return {"code": code}
