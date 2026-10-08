"""
Integration tests for POST /auth/otp/send and POST /auth/otp/verify.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import bcrypt
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.adapters.persistence.orm_models import OtpTokenRow, UserRow
from app.api.deps import get_email
from app.core.config import settings
from app.core.rate_limit import limiter
from app.main import app
from tests.fakes import EmailFake, expired_token


async def _seed_otp(engine: AsyncEngine, email: str, code: str, expired: bool = False) -> None:
    code_hash = bcrypt.hashpw(code.encode(), bcrypt.gensalt()).decode()
    expires_at = datetime.now(UTC) + timedelta(minutes=-1 if expired else 5)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(OtpTokenRow(email=email, code_hash=code_hash, expires_at=expires_at))
        await session.commit()


async def test_send_otp_accepts_valid_email(client: AsyncClient) -> None:
    resp = await client.post(
        "/auth/otp/send", json={"email": "user@example.com", "terms_accepted": True}
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_send_otp_rejects_invalid_email(client: AsyncClient) -> None:
    resp = await client.post(
        "/auth/otp/send", json={"email": "not-an-email", "terms_accepted": True}
    )
    assert resp.status_code == 422


async def test_send_otp_rejects_when_terms_not_accepted(client: AsyncClient) -> None:
    resp = await client.post(
        "/auth/otp/send", json={"email": "user@example.com", "terms_accepted": False}
    )
    assert resp.status_code == 400


async def test_send_otp_replaces_existing_token(
    client: AsyncClient, db_engine: AsyncEngine
) -> None:
    await _seed_otp(db_engine, "user@example.com", "111111")
    # Second send should not fail — replaces the old token
    resp = await client.post(
        "/auth/otp/send", json={"email": "user@example.com", "terms_accepted": True}
    )
    assert resp.status_code == 200


async def test_verify_otp_correct_code_returns_user(
    client: AsyncClient, db_engine: AsyncEngine
) -> None:
    await _seed_otp(db_engine, "user@example.com", "123456")
    resp = await client.post(
        "/auth/otp/verify", json={"email": "user@example.com", "code": "123456"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "user@example.com"
    assert body["id"]  # non-empty UUID string


async def test_verify_otp_creates_user_on_first_verify(
    client: AsyncClient, db_engine: AsyncEngine
) -> None:
    await _seed_otp(db_engine, "new@example.com", "000000")
    r1 = await client.post("/auth/otp/verify", json={"email": "new@example.com", "code": "000000"})
    assert r1.status_code == 200
    user_id = r1.json()["id"]

    # Second verify with fresh token returns same user ID
    await _seed_otp(db_engine, "new@example.com", "111111")
    r2 = await client.post("/auth/otp/verify", json={"email": "new@example.com", "code": "111111"})
    assert r2.status_code == 200
    assert r2.json()["id"] == user_id


async def test_verify_otp_stamps_terms_accepted_at_for_new_user(
    client: AsyncClient, db_engine: AsyncEngine
) -> None:
    await _seed_otp(db_engine, "consenting@example.com", "444444")
    resp = await client.post(
        "/auth/otp/verify", json={"email": "consenting@example.com", "code": "444444"}
    )
    assert resp.status_code == 200

    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        result = await session.execute(
            select(UserRow).where(UserRow.email == "consenting@example.com")
        )
        user = result.scalar_one()
        assert user.terms_accepted_at is not None


async def test_verify_otp_sends_new_user_notification_once(
    client: AsyncClient, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "debug", False)
    email_fake = EmailFake()
    app.dependency_overrides[get_email] = lambda: email_fake
    try:
        await _seed_otp(db_engine, "brandnew@example.com", "222222")
        r1 = await client.post(
            "/auth/otp/verify", json={"email": "brandnew@example.com", "code": "222222"}
        )
        assert r1.status_code == 200
        assert len(email_fake.new_user_notifications) == 1
        assert email_fake.new_user_notifications[0]["user_email"] == "brandnew@example.com"

        # Repeat verify for the same email must not send a second notification
        await _seed_otp(db_engine, "brandnew@example.com", "333333")
        r2 = await client.post(
            "/auth/otp/verify", json={"email": "brandnew@example.com", "code": "333333"}
        )
        assert r2.status_code == 200
        assert len(email_fake.new_user_notifications) == 1
    finally:
        app.dependency_overrides[get_email] = lambda: EmailFake()


async def test_verify_otp_skips_new_user_notification_when_debug(
    client: AsyncClient, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Local/test envs run with settings.debug=true — new-user notifications should only ever
    # reach the real admin inbox from prod.
    monkeypatch.setattr(settings, "debug", True)
    email_fake = EmailFake()
    app.dependency_overrides[get_email] = lambda: email_fake
    try:
        await _seed_otp(db_engine, "brandnew-debug@example.com", "222222")
        r1 = await client.post(
            "/auth/otp/verify", json={"email": "brandnew-debug@example.com", "code": "222222"}
        )
        assert r1.status_code == 200
        assert len(email_fake.new_user_notifications) == 0
    finally:
        app.dependency_overrides[get_email] = lambda: EmailFake()


async def test_verify_otp_wrong_code_returns_401(
    client: AsyncClient, db_engine: AsyncEngine
) -> None:
    await _seed_otp(db_engine, "user@example.com", "123456")
    resp = await client.post(
        "/auth/otp/verify", json={"email": "user@example.com", "code": "999999"}
    )
    assert resp.status_code == 401


async def test_verify_otp_expired_token_returns_401(
    client: AsyncClient, db_engine: AsyncEngine
) -> None:
    await _seed_otp(db_engine, "user@example.com", "123456", expired=True)
    resp = await client.post(
        "/auth/otp/verify", json={"email": "user@example.com", "code": "123456"}
    )
    assert resp.status_code == 401


async def test_verify_otp_no_token_returns_401(client: AsyncClient) -> None:
    resp = await client.post(
        "/auth/otp/verify", json={"email": "nobody@example.com", "code": "000000"}
    )
    assert resp.status_code == 401


async def test_verify_otp_consumed_after_use(client: AsyncClient, db_engine: AsyncEngine) -> None:
    await _seed_otp(db_engine, "user@example.com", "123456")
    await client.post("/auth/otp/verify", json={"email": "user@example.com", "code": "123456"})
    # Replaying the same code must fail — token was deleted on first use
    resp = await client.post(
        "/auth/otp/verify", json={"email": "user@example.com", "code": "123456"}
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Session 10b — JWT expiry
# ---------------------------------------------------------------------------


async def test_expired_bearer_jwt_rejected(client: AsyncClient) -> None:
    resp = await client.get("/jobs", headers={"Authorization": f"Bearer {expired_token()}"})
    assert resp.status_code == 401


async def test_verify_otp_assigns_expert_role_from_config(
    client: AsyncClient, db_engine: AsyncEngine
) -> None:
    expert_email = "configured-expert@example.com"
    await _seed_otp(db_engine, expert_email, "777777")

    with patch("app.api.routes.auth.settings") as mock_settings:
        mock_settings.admin_emails_set = frozenset()
        mock_settings.expert_review_emails_set = frozenset({expert_email})

        resp = await client.post("/auth/otp/verify", json={"email": expert_email, "code": "777777"})

    assert resp.status_code == 200
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        result = await session.execute(select(UserRow).where(UserRow.email == expert_email))
        user = result.scalar_one()
        assert user.role == "expert_review"


# ---------------------------------------------------------------------------
# Phase 1 — rate limiting + Turnstile CAPTCHA
# ---------------------------------------------------------------------------


async def test_send_otp_rate_limited_after_threshold(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Forced on regardless of settings.debug (locally debug=true disables the limiter entirely —
    # see app/core/rate_limit.py) so this test is deterministic on every machine and in CI alike.
    monkeypatch.setattr(limiter, "enabled", True)
    for _ in range(3):
        resp = await client.post(
            "/auth/otp/send", json={"email": "hammer@example.com", "terms_accepted": True}
        )
        assert resp.status_code == 200
    resp = await client.post(
        "/auth/otp/send", json={"email": "hammer@example.com", "terms_accepted": True}
    )
    assert resp.status_code == 429


async def test_send_otp_rejects_invalid_turnstile_token(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "turnstile_secret_key", "test-secret")
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr("app.api.routes.auth._verify_turnstile", AsyncMock(return_value=False))
    resp = await client.post(
        "/auth/otp/send",
        json={"email": "captcha@example.com", "terms_accepted": True, "turnstile_token": "bad"},
    )
    assert resp.status_code == 400


async def test_send_otp_accepts_valid_turnstile_token(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "turnstile_secret_key", "test-secret")
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr("app.api.routes.auth._verify_turnstile", AsyncMock(return_value=True))
    resp = await client.post(
        "/auth/otp/send",
        json={
            "email": "captcha-ok@example.com",
            "terms_accepted": True,
            "turnstile_token": "good",
        },
    )
    assert resp.status_code == 200


async def test_send_otp_skips_turnstile_unconfigured(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Default state (no TURNSTILE_SECRET_KEY set anywhere) — verification is a no-op, matching
    # how resend_api_key/sentry_dsn are treated when unset.
    monkeypatch.setattr(settings, "turnstile_secret_key", "")
    resp = await client.post(
        "/auth/otp/send", json={"email": "no-captcha@example.com", "terms_accepted": True}
    )
    assert resp.status_code == 200


async def test_send_otp_e2e_header_skips_turnstile_when_debug(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "turnstile_secret_key", "test-secret")
    monkeypatch.setattr(settings, "debug", True)
    verify_mock = AsyncMock(side_effect=AssertionError("should not be called"))
    monkeypatch.setattr("app.api.routes.auth._verify_turnstile", verify_mock)
    resp = await client.post(
        "/auth/otp/send",
        json={"email": "e2e@example.com", "terms_accepted": True},
        headers={"X-E2E-Skip-Turnstile": "1"},
    )
    assert resp.status_code == 200
    verify_mock.assert_not_called()


async def test_send_otp_e2e_header_ignored_outside_debug(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The bypass header must never work in prod (settings.debug=false) — otherwise it's a
    # standing CAPTCHA bypass for anyone who sends the header.
    monkeypatch.setattr(settings, "turnstile_secret_key", "test-secret")
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr("app.api.routes.auth._verify_turnstile", AsyncMock(return_value=False))
    resp = await client.post(
        "/auth/otp/send",
        json={"email": "e2e-prod@example.com", "terms_accepted": True},
        headers={"X-E2E-Skip-Turnstile": "1"},
    )
    assert resp.status_code == 400
