"""
Session 11 — Real-AI end-to-end integration tests.

Run with:
    pytest -m integration

Skipped automatically when ANTHROPIC_API_KEY is not set.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.adapters.renderer.xhtml2pdf import Xhtml2pdfAdapter
from app.adapters.vision_llm.anthropic import AnthropicAdapter
from app.api.deps import get_email, get_renderer, get_storage, get_vision_llm
from app.core.config import settings
from app.core.db import get_session
from app.main import app
from tests.fakes import EmailFake, StorageFake, auth_headers, auth_token

pytestmark = pytest.mark.integration

_SAMPLE_PHOTO = Path(__file__).parent.parent.parent / "docs" / "clusterindex" / "pics" / "2.jpg"


@pytest.fixture
def anthropic_key() -> str:
    key = settings.anthropic_api_key
    if not key:
        pytest.skip("ANTHROPIC_API_KEY not set")
    return key


@pytest.fixture
async def e2e_client(
    db_engine: AsyncEngine, anthropic_key: str
) -> AsyncGenerator[tuple[AsyncClient, StorageFake]]:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    storage = StorageFake()
    vision_llm = AnthropicAdapter(api_key=anthropic_key, storage=storage)
    renderer = Xhtml2pdfAdapter()
    email = EmailFake()

    async def _get_session() -> AsyncGenerator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _get_session
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_vision_llm] = lambda: vision_llm
    app.dependency_overrides[get_renderer] = lambda: renderer
    app.dependency_overrides[get_email] = lambda: email

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, storage

    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_storage, None)
    app.dependency_overrides.pop(get_vision_llm, None)
    app.dependency_overrides.pop(get_renderer, None)
    app.dependency_overrides.pop(get_email, None)


def _parse_sse(text: str) -> list[dict]:  # type: ignore[type-arg]
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


async def test_anthropic_assesses_real_photo(anthropic_key: str) -> None:
    storage = StorageFake()
    adapter = AnthropicAdapter(api_key=anthropic_key, storage=storage)

    photo_data = _SAMPLE_PHOTO.read_bytes()
    key = "test/photo.jpg"
    await storage.upload(key, photo_data, "image/jpeg")

    result = await adapter.assess([key], {})

    assert result.defect_type and len(result.defect_type) > 0
    assert result.severity in {"low", "medium", "high", "critical"}
    assert result.summary


async def test_full_e2e_real_ai(
    e2e_client: tuple[AsyncClient, StorageFake],
) -> None:
    client, storage = e2e_client

    photo_data = _SAMPLE_PHOTO.read_bytes()

    upload_resp = await client.post(
        "/upload",
        files=[("files", ("wall.jpg", photo_data, "image/jpeg"))],
        headers=auth_headers(),
    )
    assert upload_resp.status_code == 201, upload_resp.text
    job_id = upload_resp.json()["job_id"]

    assess_resp = await client.get(
        f"/assess/{job_id}/stream?token={auth_token()}",
        timeout=120.0,
    )
    assert assess_resp.status_code == 200

    events = _parse_sse(assess_resp.text)
    types = [e["type"] for e in events]
    assert "progress" in types
    assert "complete" in types, f"No complete event; got: {events}"
    complete_event = next(e for e in events if e["type"] == "complete")
    assert complete_event["report_url"] is not None

    report_resp = await client.get(f"/report/{job_id}", headers=auth_headers())
    assert report_resp.status_code == 200

    body = report_resp.json()
    assert body["status"] == "complete"
    assert body["defect_type"] is not None
    assert body["severity"] is not None
    assert body["report_url"] is not None

    pdf_keys = [k for k in storage._data if k.endswith(".pdf")]
    assert pdf_keys, "No PDF found in StorageFake"
    pdf_bytes = storage._data[pdf_keys[0]]
    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b"%PDF")
