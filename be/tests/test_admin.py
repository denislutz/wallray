"""Tests for /admin/reviews endpoint."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.pg_job_repo import PostgresJobRepository
from app.core.config import settings
from app.domain.job import JobStatus
from tests.fakes import TEST_USER_ID, StorageFake, auth_headers, make_jpeg

# Expert whose email must be in settings.expert_review_emails_set during tests
_EXPERT_ID = "00000000-0000-0000-0000-000000000010"
_EXPERT_EMAIL = f"test-{_EXPERT_ID}@test.local"
_OTHER_EXPERT_ID = "00000000-0000-0000-0000-000000000011"
_OTHER_EMAIL = f"test-{_OTHER_EXPERT_ID}@test.local"


@pytest.fixture(autouse=True)
def expert_role(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "expert_review_emails", f"{_EXPERT_EMAIL},{_OTHER_EMAIL}")


async def _upload_expert_job(client: AsyncClient, expert_id: str) -> str:
    img = make_jpeg()
    resp = await client.post(
        "/upload",
        files=[("files", ("photo.jpg", img, "image/jpeg"))],
        data={
            "description": "test crack",
            "assigned_expert_id": expert_id,
            "request_expert_review": "true",
        },
        headers=auth_headers(TEST_USER_ID),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["job_id"]


async def test_reviews_empty(client: AsyncClient) -> None:
    resp = await client.get("/admin/reviews", headers=auth_headers(_EXPERT_ID))
    assert resp.status_code == 200
    assert resp.json() == []


async def test_reviews_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/admin/reviews")
    assert resp.status_code == 401


async def test_reviews_requires_expert_role(client: AsyncClient) -> None:
    resp = await client.get("/admin/reviews", headers=auth_headers(TEST_USER_ID))
    assert resp.status_code == 403


async def test_reviews_returns_assigned_jobs_in_expert_review_status(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    job_id = await _upload_expert_job(client, _EXPERT_ID)

    repo = PostgresJobRepository(db_session)
    await repo.update_status(job_id, JobStatus.expert_review, assigned_expert_id=_EXPERT_ID)

    resp = await client.get("/admin/reviews", headers=auth_headers(_EXPERT_ID))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == job_id
    assert data[0]["status"] == "expert_review"


async def test_reviews_scoped_to_current_expert(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    job_id = await _upload_expert_job(client, _EXPERT_ID)

    repo = PostgresJobRepository(db_session)
    await repo.update_status(job_id, JobStatus.expert_review, assigned_expert_id=_EXPERT_ID)

    # Other expert sees an empty list
    resp = await client.get("/admin/reviews", headers=auth_headers(_OTHER_EXPERT_ID))
    assert resp.status_code == 200
    assert resp.json() == []

    # Assigned expert sees the job
    resp = await client.get("/admin/reviews", headers=auth_headers(_EXPERT_ID))
    assert resp.status_code == 200
    assert len(resp.json()) == 1


async def test_get_job_for_review_includes_photo_thumb_urls(
    client: AsyncClient,
    storage_fake: StorageFake,
    db_session: AsyncSession,
) -> None:
    """GET /admin/jobs/{id} must return photo_thumb_urls alongside photo_urls."""
    job_id = await _upload_expert_job(client, _EXPERT_ID)

    repo = PostgresJobRepository(db_session)
    await repo.update_status(job_id, JobStatus.expert_review, assigned_expert_id=_EXPERT_ID)

    resp = await client.get(f"/admin/jobs/{job_id}", headers=auth_headers(_EXPERT_ID))
    assert resp.status_code == 200
    data = resp.json()

    assert data["photo_urls"] is not None
    assert len(data["photo_urls"]) == 1
    assert data["photo_thumb_urls"] is not None
    assert len(data["photo_thumb_urls"]) == 1
    # Thumb URL must differ from the full-size URL
    assert data["photo_thumb_urls"][0] != data["photo_urls"][0]
    assert "/thumbs/" in data["photo_thumb_urls"][0]


async def test_get_job_for_review_prefers_summary_expert(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The expert view must show the expert-language synthesis when it exists,
    falling back to the customer-language summary only when languages match."""
    job_id = await _upload_expert_job(client, _EXPERT_ID)

    repo = PostgresJobRepository(db_session)
    await repo.update_status(
        job_id,
        JobStatus.complete,
        assigned_expert_id=_EXPERT_ID,
        summary="Customer-language summary.",
        summary_expert="Expert-language summary.",
    )

    resp = await client.get(f"/admin/jobs/{job_id}", headers=auth_headers(_EXPERT_ID))
    assert resp.status_code == 200
    assert resp.json()["summary"] == "Expert-language summary."


async def test_get_job_for_review_falls_back_to_summary(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    job_id = await _upload_expert_job(client, _EXPERT_ID)

    repo = PostgresJobRepository(db_session)
    await repo.update_status(
        job_id,
        JobStatus.complete,
        assigned_expert_id=_EXPERT_ID,
        summary="Only summary present.",
    )

    resp = await client.get(f"/admin/jobs/{job_id}", headers=auth_headers(_EXPERT_ID))
    assert resp.status_code == 200
    assert resp.json()["summary"] == "Only summary present."


async def test_get_job_for_review_thumb_urls_match_count(
    client: AsyncClient,
    storage_fake: StorageFake,
    db_session: AsyncSession,
) -> None:
    """photo_thumb_urls length must equal photo_urls length."""
    img = make_jpeg()
    resp = await client.post(
        "/upload",
        files=[
            ("files", ("p1.jpg", img, "image/jpeg")),
            ("files", ("p2.jpg", img, "image/jpeg")),
        ],
        data={"assigned_expert_id": _EXPERT_ID, "request_expert_review": "true"},
        headers=auth_headers(TEST_USER_ID),
    )
    assert resp.status_code == 201
    job_id = resp.json()["job_id"]

    repo = PostgresJobRepository(db_session)
    await repo.update_status(job_id, JobStatus.expert_review, assigned_expert_id=_EXPERT_ID)

    resp = await client.get(f"/admin/jobs/{job_id}", headers=auth_headers(_EXPERT_ID))
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["photo_urls"]) == len(data["photo_thumb_urls"]) == 2
