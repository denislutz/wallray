"""
Tests for RunAssessment use case, GetReport use case, and GET /report/{job_id}.
"""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.application.generate_report import GenerateReport
from app.application.get_report import GetReport, JobNotFoundError
from app.application.respond_to_job import RespondToJob
from app.application.run_assessment import RunAssessment
from app.domain.job import Job, JobStatus, Photo
from app.domain.user import User
from tests.fakes import (
    TEST_USER_ID,
    EmailFake,
    JobRepoFake,
    RendererStub,
    StorageFake,
    UserRepoFake,
    VisionLLMStub,
    auth_headers,
    make_job,
    make_jpeg,
)


def _uc(
    storage: StorageFake,
    job_repo: JobRepoFake,
    user_repo: UserRepoFake,
    email: EmailFake | None = None,
) -> RunAssessment:
    return RunAssessment(
        storage=storage,
        job_repo=job_repo,
        user_repo=user_repo,
        vision_llm=VisionLLMStub(),
        renderer=RendererStub(),
        email=email or EmailFake(),
        fe_base_url="http://localhost:3000",
    )


def _respond_uc(
    storage: StorageFake,
    job_repo: JobRepoFake,
    user_repo: UserRepoFake,
    email: EmailFake | None = None,
) -> RespondToJob:
    return RespondToJob(
        storage=storage,
        job_repo=job_repo,
        user_repo=user_repo,
        vision_llm=VisionLLMStub(),
        renderer=RendererStub(),
        email=email or EmailFake(),
        fe_base_url="http://localhost:3000",
    )


async def _upload_photos(client: AsyncClient, n: int = 2) -> str:
    resp = await client.post(
        "/upload",
        files=[("files", (f"p{i}.jpg", make_jpeg(600, 600), "image/jpeg")) for i in range(n)],
        headers=auth_headers(),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["job_id"]


# ---------------------------------------------------------------------------
# RunAssessment — unit tests
# ---------------------------------------------------------------------------


async def test_run_pauses_for_customer_input() -> None:
    """With the default customer_after_questions=1, RunAssessment always pauses for one
    reply-or-accept round instead of completing the job directly — see AI_ASSESSMENT_REWORK.md
    "await_customer_answers"."""
    storage, job_repo, user_repo = StorageFake(), JobRepoFake(), UserRepoFake()
    job_id = "job-1"
    keys = [f"jobs/{job_id}/p{i}" for i in range(2)]
    for key in keys:
        await storage.upload(key, make_jpeg(600, 600), "image/jpeg")
    await job_repo.save(make_job(job_id, keys, user_id=TEST_USER_ID))

    await _uc(storage, job_repo, user_repo).run(job_id, TEST_USER_ID)

    assert job_repo._jobs[job_id].status == JobStatus.awaiting_customer_input
    assert job_repo._jobs[job_id].report_key is None


async def test_run_does_not_increment_before_customer_responds() -> None:
    storage, job_repo, user_repo = StorageFake(), JobRepoFake(), UserRepoFake()
    job_id = "job-1"
    keys = [f"jobs/{job_id}/p{i}" for i in range(2)]
    for key in keys:
        await storage.upload(key, make_jpeg(600, 600), "image/jpeg")
    await job_repo.save(make_job(job_id, keys, user_id=TEST_USER_ID))

    await _uc(storage, job_repo, user_repo).run(job_id, TEST_USER_ID)

    assert user_repo.increments == []


async def test_run_then_accept_completes_job_with_no_second_llm_call() -> None:
    """The full happy path: RunAssessment pauses, the customer accepts without replying, and
    the job completes without a second ai_assessment call — accept must be free."""
    storage, job_repo, user_repo = StorageFake(), JobRepoFake(), UserRepoFake()
    job_id = "job-1"
    keys = [f"jobs/{job_id}/p{i}" for i in range(2)]
    for key in keys:
        await storage.upload(key, make_jpeg(600, 600), "image/jpeg")
    await job_repo.save(make_job(job_id, keys, user_id=TEST_USER_ID))

    await _uc(storage, job_repo, user_repo).run(job_id, TEST_USER_ID)
    calls_after_pause = job_repo._jobs[job_id].api_call_count

    await _respond_uc(storage, job_repo, user_repo).run(job_id, TEST_USER_ID, None)

    assert job_repo._jobs[job_id].status == JobStatus.complete
    assert job_repo._jobs[job_id].api_call_count == calls_after_pause  # accept made no LLM call
    assert user_repo.increments == [TEST_USER_ID]


async def test_run_then_reply_reruns_assessment_with_context() -> None:
    """Replying folds the customer's text into context_signals and re-runs ai_assessment with
    photos — never a text-only rerun — before completing."""
    storage, job_repo, user_repo = StorageFake(), JobRepoFake(), UserRepoFake()
    job_id = "job-1"
    keys = [f"jobs/{job_id}/p{i}" for i in range(2)]
    for key in keys:
        await storage.upload(key, make_jpeg(600, 600), "image/jpeg")
    await job_repo.save(make_job(job_id, keys, user_id=TEST_USER_ID))

    await _uc(storage, job_repo, user_repo).run(job_id, TEST_USER_ID)
    calls_after_pause = job_repo._jobs[job_id].api_call_count

    await _respond_uc(storage, job_repo, user_repo).run(
        job_id, TEST_USER_ID, "There's a drip irrigation line against this wall."
    )

    job = job_repo._jobs[job_id]
    assert job.status == JobStatus.complete
    assert job.api_call_count == calls_after_pause + 1  # one more ai_assessment call
    assert job.qa_history == [
        {"round": 0, "customer_reply": "There's a drip irrigation line against this wall."}
    ]
    assert job.context_signals is not None
    assert "There's a drip irrigation line against this wall." in job.context_signals.values()
    assert user_repo.increments == [TEST_USER_ID]


async def test_run_skips_email_on_success() -> None:
    # Customer "report ready" email is disabled for now — see run_assessment.py.
    storage, job_repo, user_repo, email = (
        StorageFake(),
        JobRepoFake(),
        UserRepoFake(),
        EmailFake(),
    )
    job_id = "job-1"
    keys = [f"jobs/{job_id}/p{i}" for i in range(2)]
    for key in keys:
        await storage.upload(key, make_jpeg(600, 600), "image/jpeg")
    await user_repo._set_user(User(id=TEST_USER_ID, email="user@example.com"))
    await job_repo.save(make_job(job_id, keys, user_id=TEST_USER_ID))

    await _uc(storage, job_repo, user_repo, email).run(job_id, TEST_USER_ID)

    assert email.sent == []


async def test_run_skips_email_when_no_user_email() -> None:
    storage, job_repo, user_repo, email = (
        StorageFake(),
        JobRepoFake(),
        UserRepoFake(),
        EmailFake(),
    )
    job_id = "job-1"
    keys = [f"jobs/{job_id}/p{i}" for i in range(2)]
    for key in keys:
        await storage.upload(key, make_jpeg(600, 600), "image/jpeg")
    await job_repo.save(make_job(job_id, keys, user_id=TEST_USER_ID))
    # user_repo has no user set → get() returns None

    await _uc(storage, job_repo, user_repo, email).run(job_id, TEST_USER_ID)

    assert email.sent == []


async def test_run_ignores_unknown_job() -> None:
    storage, job_repo, user_repo = StorageFake(), JobRepoFake(), UserRepoFake()
    # Should silently return without raising
    await _uc(storage, job_repo, user_repo).run("nonexistent", TEST_USER_ID)


async def test_run_ignores_wrong_user() -> None:
    storage, job_repo, user_repo = StorageFake(), JobRepoFake(), UserRepoFake()
    job_id = "job-1"
    keys = [f"jobs/{job_id}/p0"]
    await storage.upload(keys[0], make_jpeg(), "image/jpeg")
    await job_repo.save(make_job(job_id, keys, user_id="other-user"))

    await _uc(storage, job_repo, user_repo).run(job_id, TEST_USER_ID)

    # Status unchanged — run() bailed early
    assert job_repo._jobs[job_id].status == JobStatus.pending


async def test_run_sets_failed_when_validation_fails() -> None:
    storage, job_repo, user_repo = StorageFake(), JobRepoFake(), UserRepoFake()
    job_id = "job-1"
    # No photo keys → validation fails (zero photos)
    await job_repo.save(make_job(job_id, [], user_id=TEST_USER_ID))

    await _uc(storage, job_repo, user_repo).run(job_id, TEST_USER_ID)

    assert job_repo._jobs[job_id].status == JobStatus.failed
    assert user_repo.increments == []


async def test_accept_never_triggers_expert_review() -> None:
    """Expert review is now a separate, explicit action at await_customer_answers — accept
    always completes the AI-only report and never notifies an expert, even if the job carries
    a stale request_expert_review flag from before this amendment."""
    storage, job_repo, user_repo, email = (
        StorageFake(),
        JobRepoFake(),
        UserRepoFake(),
        EmailFake(),
    )
    job_id = "job-1"
    keys = [f"jobs/{job_id}/p{i}" for i in range(2)]
    for key in keys:
        await storage.upload(key, make_jpeg(600, 600), "image/jpeg")
    await job_repo.save(make_job(job_id, keys, user_id=TEST_USER_ID, request_expert_review=True))

    await _uc(storage, job_repo, user_repo, email).run(job_id, TEST_USER_ID)
    await _respond_uc(storage, job_repo, user_repo, email).run(job_id, TEST_USER_ID, None)

    assert job_repo._jobs[job_id].status == JobStatus.complete
    assert email.expert_requests == []


async def test_respond_request_expert_skips_report_generator() -> None:
    """Requesting expert review at await_customer_answers routes straight to expert_notifier
    — no AI-only PDF is ever rendered, and report_key stays null until the expert submits
    notes (GenerateReport renders the first PDF this job gets on this path)."""
    storage, job_repo, user_repo, email = (
        StorageFake(),
        JobRepoFake(),
        UserRepoFake(),
        EmailFake(),
    )
    job_id = "job-1"
    keys = [f"jobs/{job_id}/p{i}" for i in range(2)]
    for key in keys:
        await storage.upload(key, make_jpeg(600, 600), "image/jpeg")
    await job_repo.save(make_job(job_id, keys, user_id=TEST_USER_ID))
    await user_repo._set_user(User(id="expert-1", email="expert@example.com"))

    await _uc(storage, job_repo, user_repo).run(job_id, TEST_USER_ID)
    await _respond_uc(storage, job_repo, user_repo, email).run(
        job_id, TEST_USER_ID, None, request_expert_review=True, assigned_expert_id="expert-1"
    )

    job = job_repo._jobs[job_id]
    assert job.status == JobStatus.expert_review
    assert job.report_key is None
    assert "jobs/job-1/report.pdf" not in storage._data
    assert len(email.expert_requests) == 1
    assert user_repo.increments == [TEST_USER_ID]


# ---------------------------------------------------------------------------
# GetReport use case — unit tests
# ---------------------------------------------------------------------------


async def test_get_report_returns_resolved_job() -> None:
    storage = StorageFake()
    job_repo = JobRepoFake()

    job_id = "job-1"
    key = f"jobs/{job_id}/p0"
    await storage.upload(key, make_jpeg(), "image/jpeg")
    job = Job(
        id=job_id,
        user_id=TEST_USER_ID,
        status=JobStatus.complete,
        photos=[Photo(key=key, content_type="image/jpeg")],
        description="Damp wall",
        created_at=datetime.now(UTC),
        thumbnail_key=key,
        defect_type="damp",
        severity="low",
        report_key=f"jobs/{job_id}/report.pdf",
    )
    await storage.upload(f"jobs/{job_id}/report.pdf", b"%PDF-1", "application/pdf")
    await job_repo.save(job)

    resolved = await GetReport(storage, job_repo, UserRepoFake(), VisionLLMStub()).execute(
        job_id, TEST_USER_ID
    )

    assert resolved.id == job_id
    assert resolved.status == "complete"
    assert resolved.description == "Damp wall"
    assert resolved.defect_type == "damp"
    assert resolved.severity == "low"
    assert resolved.thumbnail_url is not None
    assert resolved.report_url is not None


async def test_get_report_raises_for_unknown_job() -> None:
    storage = StorageFake()
    job_repo = JobRepoFake()

    with pytest.raises(JobNotFoundError):
        await GetReport(storage, job_repo, UserRepoFake(), VisionLLMStub()).execute(
            "nonexistent", TEST_USER_ID
        )


async def test_get_report_raises_for_wrong_user() -> None:
    storage = StorageFake()
    job_repo = JobRepoFake()

    job_id = "job-1"
    keys = [f"jobs/{job_id}/p0"]
    await storage.upload(keys[0], make_jpeg(), "image/jpeg")
    await job_repo.save(make_job(job_id, keys, user_id="other-user"))

    with pytest.raises(JobNotFoundError):
        await GetReport(storage, job_repo, UserRepoFake(), VisionLLMStub()).execute(
            job_id, TEST_USER_ID
        )


async def test_get_report_no_report_url_when_pending() -> None:
    storage = StorageFake()
    job_repo = JobRepoFake()

    job_id = "job-1"
    keys = [f"jobs/{job_id}/p0"]
    await storage.upload(keys[0], make_jpeg(), "image/jpeg")
    await job_repo.save(make_job(job_id, keys, user_id=TEST_USER_ID))

    resolved = await GetReport(storage, job_repo, UserRepoFake(), VisionLLMStub()).execute(
        job_id, TEST_USER_ID
    )
    assert resolved.report_url is None


async def test_get_report_exposes_expert_notes() -> None:
    storage = StorageFake()
    job_repo = JobRepoFake()

    job_id = "job-1"
    key = f"jobs/{job_id}/p0"
    await storage.upload(key, make_jpeg(), "image/jpeg")
    job = Job(
        id=job_id,
        user_id=TEST_USER_ID,
        status=JobStatus.complete,
        photos=[Photo(key=key, content_type="image/jpeg")],
        description=None,
        created_at=datetime.now(UTC),
        thumbnail_key=key,
        report_key=f"jobs/{job_id}/report.pdf",
        expert_notes="Crack is structural.",
    )
    await storage.upload(f"jobs/{job_id}/report.pdf", b"%PDF-1", "application/pdf")
    await job_repo.save(job)

    resolved = await GetReport(storage, job_repo, UserRepoFake(), VisionLLMStub()).execute(
        job_id, TEST_USER_ID
    )
    assert resolved.expert_notes == "Crack is structural."


async def test_get_report_exposes_photos_and_notes_before_expert_review() -> None:
    """Customer must see AI photos + the assessment summary even while awaiting expert review."""
    storage = StorageFake()
    job_repo = JobRepoFake()

    job_id = "job-1"
    keys = [f"jobs/{job_id}/p0", f"jobs/{job_id}/p1"]
    for key in keys:
        await storage.upload(key, make_jpeg(), "image/jpeg")
    job = Job(
        id=job_id,
        user_id=TEST_USER_ID,
        status=JobStatus.expert_review,
        photos=[Photo(key=k, content_type="image/jpeg") for k in keys],
        description=None,
        created_at=datetime.now(UTC),
        thumbnail_key=keys[0],
        defect_type="crack",
        severity="high",
        summary="Hairline crack.",
        request_expert_review=True,
    )
    await job_repo.save(job)

    resolved = await GetReport(storage, job_repo, UserRepoFake(), VisionLLMStub()).execute(
        job_id, TEST_USER_ID
    )

    assert resolved.report_url is None  # not complete yet
    assert resolved.photo_urls is not None
    assert len(resolved.photo_urls) == 2
    assert resolved.summary == "Hairline crack."


async def test_get_report_exposes_summary() -> None:
    """The final synthesized review must reach the customer-facing resolved job,
    rendered after the expert field in the FE — see ReportView.tsx."""
    storage = StorageFake()
    job_repo = JobRepoFake()

    job_id = "job-1"
    key = f"jobs/{job_id}/p0"
    await storage.upload(key, make_jpeg(), "image/jpeg")
    job = Job(
        id=job_id,
        user_id=TEST_USER_ID,
        status=JobStatus.complete,
        photos=[Photo(key=key, content_type="image/jpeg")],
        description=None,
        created_at=datetime.now(UTC),
        thumbnail_key=key,
        report_key=f"jobs/{job_id}/report.pdf",
        summary="Final synthesized assessment.",
    )
    await storage.upload(f"jobs/{job_id}/report.pdf", b"%PDF-1", "application/pdf")
    await job_repo.save(job)

    resolved = await GetReport(storage, job_repo, UserRepoFake(), VisionLLMStub()).execute(
        job_id, TEST_USER_ID
    )
    assert resolved.summary == "Final synthesized assessment."


# ---------------------------------------------------------------------------
# GET /report/{job_id} — HTTP tests
# ---------------------------------------------------------------------------


async def test_get_report_endpoint_returns_job_after_upload(client: AsyncClient) -> None:
    resp = await client.post(
        "/upload",
        files=[("files", ("p0.jpg", make_jpeg(), "image/jpeg"))],
        headers=auth_headers(),
    )
    assert resp.status_code == 201
    job_id = resp.json()["job_id"]

    resp = await client.get(f"/report/{job_id}", headers=auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == job_id
    # Background task runs synchronously in tests
    assert body["status"] in (
        "pending",
        "processing",
        "awaiting_customer_input",
        "complete",
        "failed",
    )


async def test_get_report_endpoint_pauses_for_customer_input_after_upload(
    assess_client: AsyncClient,
) -> None:
    # With assess_client, background task runs synchronously — with the default
    # customer_after_questions=1, it pauses rather than completing directly.
    job_id = await _upload_photos(assess_client)

    resp = await assess_client.get(f"/report/{job_id}", headers=auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "awaiting_customer_input"
    assert body["defect_type"] is not None
    assert body["severity"] is not None
    assert body["report_url"] is None


async def test_respond_accept_completes_the_job(assess_client: AsyncClient) -> None:
    job_id = await _upload_photos(assess_client)

    resp = await assess_client.post(
        f"/jobs/{job_id}/respond", json={"reply": None}, headers=auth_headers()
    )
    assert resp.status_code == 200, resp.text

    resp = await assess_client.get(f"/report/{job_id}", headers=auth_headers())
    body = resp.json()
    assert body["status"] == "complete"
    assert body["report_url"] is not None


async def test_respond_reply_completes_the_job_after_second_assessment(
    assess_client: AsyncClient,
) -> None:
    job_id = await _upload_photos(assess_client)

    resp = await assess_client.post(
        f"/jobs/{job_id}/respond",
        json={"reply": "The wall faces north, no direct sun."},
        headers=auth_headers(),
    )
    assert resp.status_code == 200, resp.text

    resp = await assess_client.get(f"/report/{job_id}", headers=auth_headers())
    body = resp.json()
    assert body["status"] == "complete"
    assert body["report_url"] is not None


async def test_respond_request_expert_review_via_http(assess_client: AsyncClient) -> None:
    job_id = await _upload_photos(assess_client)

    resp = await assess_client.post(
        f"/jobs/{job_id}/respond",
        json={
            "request_expert_review": True,
            "assigned_expert_id": "00000000-0000-0000-0000-000000000099",
        },
        headers=auth_headers(),
    )
    assert resp.status_code == 200, resp.text

    resp = await assess_client.get(f"/report/{job_id}", headers=auth_headers())
    body = resp.json()
    assert body["status"] == "expert_review"
    assert body["report_url"] is None


async def test_respond_requires_assigned_expert_when_requesting_review(
    assess_client: AsyncClient,
) -> None:
    job_id = await _upload_photos(assess_client)

    resp = await assess_client.post(
        f"/jobs/{job_id}/respond",
        json={"request_expert_review": True},
        headers=auth_headers(),
    )
    assert resp.status_code == 422


async def test_respond_404_for_wrong_user(assess_client: AsyncClient) -> None:
    job_id = await _upload_photos(assess_client)
    other = "00000000-0000-0000-0000-000000000002"

    resp = await assess_client.post(
        f"/jobs/{job_id}/respond", json={"reply": None}, headers=auth_headers(other)
    )
    assert resp.status_code == 404


async def test_respond_409_when_not_awaiting_customer_input(client: AsyncClient) -> None:
    resp = await client.post(
        "/upload",
        files=[("files", ("p0.jpg", make_jpeg(), "image/jpeg"))],
        headers=auth_headers(),
    )
    job_id = resp.json()["job_id"]

    # First respond resolves the only pending round; a second respond has nothing to answer.
    await client.post(f"/jobs/{job_id}/respond", json={"reply": None}, headers=auth_headers())

    resp = await client.post(
        f"/jobs/{job_id}/respond", json={"reply": None}, headers=auth_headers()
    )
    assert resp.status_code == 409


async def test_upload_persists_customer_language_through_real_repository(
    assess_client: AsyncClient,
) -> None:
    """Regression test: PostgresJobRepository.save() must persist customer_language.

    Uses assess_client (real HTTP request -> real SQLAlchemy session -> real
    PostgresJobRepository, not JobRepoFake) so it exercises the exact code path
    where the field was previously silently dropped from the INSERT and fell
    back to the DB's server_default ("en").
    """
    resp = await assess_client.post(
        "/upload",
        files=[("files", ("p0.jpg", make_jpeg(600, 600), "image/jpeg"))],
        data={"language": "de"},
        headers=auth_headers(),
    )
    assert resp.status_code == 201, resp.text
    job_id = resp.json()["job_id"]

    resp = await assess_client.get(f"/report/{job_id}", headers=auth_headers())
    assert resp.status_code == 200
    body = resp.json()
    # VisionLLMStub.assess() writes `summary` natively in customer_language, prefixing with
    # "[{customer_language}] " when it isn't "en" — only present if customer_language actually
    # made it to the DB as "de".
    assert body["summary"] is not None
    assert body["summary"].startswith("[de] ")


async def test_get_report_endpoint_404_for_unknown(client: AsyncClient) -> None:
    resp = await client.get("/report/nonexistent", headers=auth_headers())
    assert resp.status_code == 404


async def test_get_report_endpoint_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/report/some-id")
    assert resp.status_code == 401


async def test_get_report_wrong_user_returns_404(client: AsyncClient) -> None:
    resp = await client.post(
        "/upload",
        files=[("files", ("p0.jpg", make_jpeg(), "image/jpeg"))],
        headers=auth_headers(),
    )
    job_id = resp.json()["job_id"]
    other = "00000000-0000-0000-0000-000000000002"
    resp = await client.get(f"/report/{job_id}", headers=auth_headers(other))
    assert resp.status_code == 404


async def test_get_report_exposes_expert_notes_field(
    assess_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id = await _upload_photos(assess_client)
    resp = await assess_client.get(f"/report/{job_id}", headers=auth_headers())
    body = resp.json()
    assert "expert_notes" in body


# ---------------------------------------------------------------------------
# GenerateReport — language scenarios
# ---------------------------------------------------------------------------


def _generate_uc(
    storage: StorageFake,
    job_repo: JobRepoFake,
    user_repo: UserRepoFake,
    email: EmailFake | None = None,
) -> GenerateReport:
    return GenerateReport(
        storage=storage,
        job_repo=job_repo,
        user_repo=user_repo,
        vision_llm=VisionLLMStub(),
        renderer=RendererStub(),
        email=email or EmailFake(),
        fe_base_url="http://localhost:3000",
    )


def _reviewed_job(
    job_id: str,
    keys: list[str],
    customer_language: str,
    expert_language: str,
    assigned_expert_id: str | None = None,
) -> Job:
    return Job(
        id=job_id,
        user_id=TEST_USER_ID,
        status=JobStatus.expert_review,
        photos=[Photo(key=k, content_type="image/jpeg") for k in keys],
        description=None,
        created_at=datetime.now(UTC),
        thumbnail_key=keys[0] if keys else None,
        defect_type="crack",
        severity="high",
        summary="Hairline crack.",
        expert_notes="Crack is structural.",
        customer_language=customer_language,
        expert_language=expert_language,
        assigned_expert_id=assigned_expert_id,
    )


async def test_generate_report_cross_language_creates_two_pdfs() -> None:
    """EN customer + DE expert → summary_expert non-null → two PDFs stored."""
    storage, job_repo, user_repo = StorageFake(), JobRepoFake(), UserRepoFake()
    keys = [f"jobs/job-gl1/p{i}" for i in range(2)]
    for key in keys:
        await storage.upload(key, make_jpeg(600, 600), "image/jpeg")
    await job_repo.save(
        _reviewed_job("job-gl1", keys, customer_language="en", expert_language="de")
    )

    await _generate_uc(storage, job_repo, user_repo).run("job-gl1")

    assert "jobs/job-gl1/report.pdf" in storage._data
    assert "jobs/job-gl1/report_expert.pdf" in storage._data
    persisted = [u for u in job_repo.status_updates if "expert_report_key" in u]
    assert persisted[-1]["expert_report_key"] == "jobs/job-gl1/report_expert.pdf"
    # RendererStub encodes summary_override in PDF bytes — expert PDF must differ
    assert (
        storage._data["jobs/job-gl1/report.pdf"] != storage._data["jobs/job-gl1/report_expert.pdf"]
    )
    assert b"[de]" in storage._data["jobs/job-gl1/report_expert.pdf"]


async def test_generate_report_same_language_creates_one_pdf() -> None:
    """DE customer + DE expert → summary_expert None → only one PDF stored."""
    storage, job_repo, user_repo = StorageFake(), JobRepoFake(), UserRepoFake()
    keys = [f"jobs/job-gl2/p{i}" for i in range(2)]
    for key in keys:
        await storage.upload(key, make_jpeg(600, 600), "image/jpeg")
    await job_repo.save(
        _reviewed_job("job-gl2", keys, customer_language="de", expert_language="de")
    )

    await _generate_uc(storage, job_repo, user_repo).run("job-gl2")

    assert "jobs/job-gl2/report.pdf" in storage._data
    assert "jobs/job-gl2/report_expert.pdf" not in storage._data
    persisted = [u for u in job_repo.status_updates if "expert_report_key" in u]
    assert persisted[-1]["expert_report_key"] is None


async def test_generate_report_ru_customer_de_expert_creates_two_pdfs() -> None:
    """RU customer + DE expert → cross-language → two PDFs stored."""
    storage, job_repo, user_repo = StorageFake(), JobRepoFake(), UserRepoFake()
    keys = [f"jobs/job-gl3/p{i}" for i in range(2)]
    for key in keys:
        await storage.upload(key, make_jpeg(600, 600), "image/jpeg")
    await job_repo.save(
        _reviewed_job("job-gl3", keys, customer_language="ru", expert_language="de")
    )

    await _generate_uc(storage, job_repo, user_repo).run("job-gl3")

    assert "jobs/job-gl3/report.pdf" in storage._data
    assert "jobs/job-gl3/report_expert.pdf" in storage._data
    assert b"[de]" in storage._data["jobs/job-gl3/report_expert.pdf"]


async def test_generate_report_skips_expert_email() -> None:
    # Expert + customer "report ready" emails are disabled for now — see generate_report.py.
    storage, job_repo, user_repo, email = StorageFake(), JobRepoFake(), UserRepoFake(), EmailFake()
    keys = [f"jobs/job-gl4/p{i}" for i in range(2)]
    for key in keys:
        await storage.upload(key, make_jpeg(600, 600), "image/jpeg")
    expert = User(id="expert-1", email="expert@example.com")
    await user_repo._set_user(expert)
    job = _reviewed_job(
        "job-gl4", keys, customer_language="en", expert_language="de", assigned_expert_id="expert-1"
    )
    await job_repo.save(job)

    await _generate_uc(storage, job_repo, user_repo, email).run("job-gl4")

    assert email.sent == []
