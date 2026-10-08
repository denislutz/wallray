"""
Integration tests for POST /upload and GET /jobs.

Uses real FastAPI (via ASGITransport), real SQLAlchemy sessions (SQLite
in-memory), real use-case and domain code, and StorageFake in place of S3.
No mocks — only the external service boundary is replaced.
"""

import io

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.adapters.persistence.orm_models import UserRow
from app.core.config import settings
from tests.fakes import TEST_USER_ID, StorageFake, auth_headers, make_jpeg, make_webp

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _file(name: str = "photo.jpg", data: bytes | None = None) -> tuple[str, tuple[str, bytes, str]]:
    return ("files", (name, data or make_jpeg(), "image/jpeg"))


async def _upload(client: AsyncClient, *, n: int = 1, description: str | None = None) -> str:
    payload: dict = {"files": [_file(f"p{i}.jpg") for i in range(n)]}
    if description:
        payload["data"] = {"description": description}
    resp = await client.post(
        "/upload",
        files=payload["files"],
        data=payload.get("data"),
        headers=auth_headers(),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["job_id"]


# ---------------------------------------------------------------------------
# POST /upload
# ---------------------------------------------------------------------------


async def test_upload_returns_job_id(client: AsyncClient) -> None:
    resp = await client.post(
        "/upload",
        files=[_file()],
        headers=auth_headers(),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "job_id" in body
    assert body["job_id"]  # non-empty


async def test_upload_with_description(client: AsyncClient) -> None:
    job_id = await _upload(client, description="Crack in ceiling")

    jobs = (await client.get("/jobs", headers=auth_headers())).json()
    assert jobs[0]["id"] == job_id
    assert jobs[0]["description"] == "Crack in ceiling"


# ---------------------------------------------------------------------------
# Report name — optional, derived from description when blank
# ---------------------------------------------------------------------------


async def test_upload_blank_name_derives_from_description(client: AsyncClient) -> None:
    resp = await client.post(
        "/upload",
        files=[_file()],
        data={"description": "Crack near the kitchen window, noticed after last winter"},
        headers=auth_headers(),
    )
    assert resp.status_code == 201, resp.text

    jobs = (await client.get("/jobs", headers=auth_headers())).json()
    assert jobs[0]["name"] == "Crack near the kitchen window, noticed…"


async def test_upload_explicit_name_wins_over_description(client: AsyncClient) -> None:
    resp = await client.post(
        "/upload",
        files=[_file()],
        data={"name": "My custom title", "description": "Crack in ceiling"},
        headers=auth_headers(),
    )
    assert resp.status_code == 201, resp.text

    jobs = (await client.get("/jobs", headers=auth_headers())).json()
    assert jobs[0]["name"] == "My custom title"


async def test_upload_blank_name_and_description_stays_null(client: AsyncClient) -> None:
    resp = await client.post("/upload", files=[_file()], headers=auth_headers())
    assert resp.status_code == 201, resp.text

    jobs = (await client.get("/jobs", headers=auth_headers())).json()
    assert jobs[0]["name"] is None


async def test_upload_whitespace_only_name_derives_from_description(client: AsyncClient) -> None:
    resp = await client.post(
        "/upload",
        files=[_file()],
        data={"name": "   ", "description": "Damp patch on the wall"},
        headers=auth_headers(),
    )
    assert resp.status_code == 201, resp.text

    jobs = (await client.get("/jobs", headers=auth_headers())).json()
    assert jobs[0]["name"] == "Damp patch on the wall"


async def test_upload_rejects_wrong_mime_type(client: AsyncClient) -> None:
    resp = await client.post(
        "/upload",
        files=[("files", ("doc.pdf", b"content", "application/pdf"))],
        headers=auth_headers(),
    )
    assert resp.status_code == 422


async def test_upload_rejects_bad_magic_bytes(client: AsyncClient) -> None:
    resp = await client.post(
        "/upload",
        files=[("files", ("photo.jpg", b"not-actually-a-jpeg-xxxxx", "image/jpeg"))],
        headers=auth_headers(),
    )
    assert resp.status_code == 422


async def test_upload_free_tier_limit(client: AsyncClient, db_engine: AsyncEngine) -> None:
    # Seed a user who has already consumed their free reports
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        session.add(
            UserRow(id=TEST_USER_ID, email="t@t.com", report_count=settings.free_tier_limit)
        )
        await session.commit()

    resp = await client.post("/upload", files=[_file()], headers=auth_headers())
    assert resp.status_code == 402


async def test_upload_requires_auth(client: AsyncClient) -> None:
    resp = await client.post("/upload", files=[_file()])
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /jobs
# ---------------------------------------------------------------------------


async def test_jobs_empty_for_new_user(client: AsyncClient) -> None:
    resp = await client.get("/jobs", headers=auth_headers())
    assert resp.status_code == 200
    assert resp.json() == []


async def test_jobs_returns_uploaded_job(client: AsyncClient) -> None:
    job_id = await _upload(client, description="Damp patch")

    resp = await client.get("/jobs", headers=auth_headers())
    assert resp.status_code == 200

    jobs = resp.json()
    assert len(jobs) == 1
    job = jobs[0]

    assert job["id"] == job_id
    assert job["description"] == "Damp patch"
    assert job["thumbnail_url"].startswith("https://fake/")  # StorageFake signed URL
    # Background task runs synchronously in tests — job may already be paused for the
    # one clarification round (customer_after_questions=1 default) or complete
    assert job["status"] in (
        "pending",
        "processing",
        "awaiting_customer_input",
        "complete",
        "failed",
    )


async def test_jobs_multiple_uploads(client: AsyncClient) -> None:
    for _ in range(3):
        await _upload(client)

    jobs = (await client.get("/jobs", headers=auth_headers())).json()
    assert len(jobs) == 3


async def test_jobs_are_user_scoped(client: AsyncClient) -> None:
    user_a = auth_headers("00000000-0000-0000-0000-000000000001")
    user_b = auth_headers("00000000-0000-0000-0000-000000000002")

    await client.post("/upload", files=[_file()], headers=user_a)
    await client.post("/upload", files=[_file()], headers=user_b)
    await client.post("/upload", files=[_file()], headers=user_b)

    assert len((await client.get("/jobs", headers=user_a)).json()) == 1
    assert len((await client.get("/jobs", headers=user_b)).json()) == 2


# ---------------------------------------------------------------------------
# Session 10a — upload + jobs gap tests
# ---------------------------------------------------------------------------


async def test_upload_rejects_oversized_file(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "photo_max_size_mb", 1)
    oversized = b"\xff\xd8\xff" + b"x" * (1024 * 1024 + 1)
    resp = await client.post(
        "/upload",
        files=[("files", ("big.jpg", oversized, "image/jpeg"))],
        headers=auth_headers(),
    )
    assert resp.status_code == 422


async def test_upload_rejects_too_many_files(client: AsyncClient) -> None:
    resp = await client.post(
        "/upload",
        files=[_file(f"p{i}.jpg") for i in range(11)],
        headers=auth_headers(),
    )
    assert resp.status_code == 422


async def test_upload_accepts_webp(client: AsyncClient) -> None:
    resp = await client.post(
        "/upload",
        files=[("files", ("photo.webp", make_webp(), "image/webp"))],
        headers=auth_headers(),
    )
    assert resp.status_code == 201


async def test_upload_accepts_multiple_files(client: AsyncClient) -> None:
    resp = await client.post(
        "/upload",
        files=[("files", (f"p{i}.jpg", make_jpeg(), "image/jpeg")) for i in range(3)],
        headers=auth_headers(),
    )
    assert resp.status_code == 201

    jobs = (await client.get("/jobs", headers=auth_headers())).json()
    assert len(jobs) == 1
    assert jobs[0]["thumbnail_url"].startswith("https://fake/")


async def test_jobs_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/jobs")
    assert resp.status_code == 401


async def test_jobs_complete_job_shows_all_fields(assess_client: AsyncClient) -> None:
    # With assess_client, background task runs synchronously during upload, pausing for the
    # one clarification round (customer_after_questions=1 default) — accept it to complete.
    job_id = await _upload(assess_client)
    await assess_client.post(
        f"/jobs/{job_id}/respond", json={"reply": None}, headers=auth_headers()
    )

    jobs = (await assess_client.get("/jobs", headers=auth_headers())).json()
    assert len(jobs) == 1
    job = jobs[0]
    assert job["status"] == "complete"
    assert job["report_url"] is not None
    assert job["defect_type"] is not None
    assert job["severity"] is not None


# ---------------------------------------------------------------------------
# Thumbnail generation
# ---------------------------------------------------------------------------


async def test_upload_generates_thumbnail_key(
    client: AsyncClient, storage_fake: "StorageFake"
) -> None:
    """thumbnail_key on the stored job should point to the thumb, not the full image."""
    resp = await client.post("/upload", files=[_file()], headers=auth_headers())
    assert resp.status_code == 201
    job_id = resp.json()["job_id"]

    jobs = (await client.get("/jobs", headers=auth_headers())).json()
    job = next(j for j in jobs if j["id"] == job_id)
    # thumbnail_url is served from the thumb key — its path contains /thumbs/
    assert "/thumbs/" in job["thumbnail_url"]


async def test_upload_thumbnail_is_max_400px(
    client: AsyncClient, storage_fake: "StorageFake"
) -> None:
    """Thumbnail bytes stored by StorageFake must be ≤ 400 px on the wide side."""
    resp = await client.post(
        "/upload",
        files=[("files", ("photo.jpg", make_jpeg(width=1200, height=800), "image/jpeg"))],
        headers=auth_headers(),
    )
    assert resp.status_code == 201

    thumb_keys = [k for k in storage_fake._data if "/thumbs/" in k]
    assert len(thumb_keys) == 1

    thumb_bytes = storage_fake._data[thumb_keys[0]]
    img = Image.open(io.BytesIO(thumb_bytes))
    assert img.width <= 400
    assert img.height <= 400


async def test_upload_oversized_file_is_downscaled(
    client: AsyncClient,
    storage_fake: "StorageFake",
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A file above the resize threshold must be stored at reduced dimensions."""
    # Set threshold to 0 so any non-empty file triggers downscaling
    monkeypatch.setattr(settings, "photo_resize_threshold_mb", 0)

    resp = await client.post(
        "/upload",
        files=[("files", ("big.jpg", make_jpeg(width=600, height=400), "image/jpeg"))],
        headers=auth_headers(),
    )
    assert resp.status_code == 201

    full_keys = [
        k
        for k in storage_fake._data
        if "/thumbs/" not in k and "jobs/" in k and not k.endswith(".pdf")
    ]
    assert len(full_keys) == 1
    stored_bytes = storage_fake._data[full_keys[0]]
    img = Image.open(io.BytesIO(stored_bytes))
    # After 50% downscale dimensions must be halved
    assert img.width == 300
    assert img.height == 200


async def test_upload_small_file_not_downscaled(
    client: AsyncClient,
    storage_fake: "StorageFake",
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Files below the resize threshold are stored without downscaling."""
    monkeypatch.setattr(settings, "photo_resize_threshold_mb", 20)

    resp = await client.post("/upload", files=[_file()], headers=auth_headers())
    assert resp.status_code == 201

    full_keys = [
        k
        for k in storage_fake._data
        if "/thumbs/" not in k and "jobs/" in k and not k.endswith(".pdf")
    ]
    assert len(full_keys) == 1
    stored_bytes = storage_fake._data[full_keys[0]]
    img = Image.open(io.BytesIO(stored_bytes))
    assert img.width == 600  # make_jpeg default, unchanged
