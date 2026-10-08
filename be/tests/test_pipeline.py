from typing import Any

import pytest

from app.application.pipeline import graph
from app.application.pipeline.call_budget import CallBudgetExceededError
from app.application.pipeline.nodes.intake_gate import _MIN_DIMENSION
from app.application.pipeline.state import AssessmentState
from app.core.config import settings
from app.domain.job import JobStatus, PhotoRole
from tests.fakes import (
    EmailFake,
    JobRepoFake,
    RendererStub,
    StorageFake,
    UserRepoFake,
    VisionLLMStub,
    make_job,
    make_jpeg,
    make_png,
)


def _state(
    photo_keys: list[str],
    job_id: str = "job-1",
    customer_language: str = "en",
    qa_history: list[dict[str, Any]] | None = None,
    api_call_count: int = 0,
) -> AssessmentState:
    history = qa_history or []
    return AssessmentState(
        job_id=job_id,
        user_id="user-1",
        photo_keys=photo_keys,
        description=None,
        request_expert_review=False,
        assigned_expert_id=None,
        validation_passed=False,
        validation_errors=[],
        photo_roles={},
        context_signals={},
        defect_classification=None,
        severity=None,
        report_key=None,
        report_url=None,
        expert_notes=None,
        customer_language=customer_language,
        expert_language=None,
        confidence=None,
        verification_items=[],
        qa_history=history,
        loop_count=len(history),
        api_call_count=api_call_count,
    )


def _build(
    storage: StorageFake, job_repo: JobRepoFake, vision_llm: VisionLLMStub | None = None
) -> Any:
    return graph.build(
        storage,
        job_repo,
        UserRepoFake(),
        vision_llm or VisionLLMStub(),
        RendererStub(),
        EmailFake(),
        "",
    )


def _build_resume(storage: StorageFake, job_repo: JobRepoFake) -> Any:
    return graph.build_resume(
        storage, job_repo, UserRepoFake(), VisionLLMStub(), RendererStub(), EmailFake(), ""
    )


async def _valid_storage(storage: StorageFake, job_id: str = "job-1") -> list[str]:
    """Upload settings.photo_min_count valid JPEGs and return their keys."""
    keys = [f"jobs/{job_id}/p{i}" for i in range(settings.photo_min_count)]
    for key in keys:
        await storage.upload(key, make_jpeg(_MIN_DIMENSION, _MIN_DIMENSION), "image/jpeg")
    return keys


# ---------------------------------------------------------------------------
# intake_gate node
# ---------------------------------------------------------------------------


async def test_graph_runs_end_to_end() -> None:
    storage, job_repo = StorageFake(), JobRepoFake()
    keys = await _valid_storage(storage)
    await job_repo.save(make_job("job-1", keys))

    result = await _build(storage, job_repo).ainvoke(_state(keys))

    assert result["validation_passed"] is True
    assert result["validation_errors"] == []
    assert result["defect_classification"] is not None


async def test_intake_gate_sets_processing_status() -> None:
    storage, job_repo = StorageFake(), JobRepoFake()
    keys = await _valid_storage(storage)
    await job_repo.save(make_job("job-1", keys))

    await _build(storage, job_repo).ainvoke(_state(keys))

    assert job_repo.status_updates[0]["status"] == JobStatus.processing


async def test_intake_gate_accepts_png() -> None:
    storage, job_repo = StorageFake(), JobRepoFake()
    keys = [f"jobs/job-1/p{i}" for i in range(settings.photo_min_count)]
    for key in keys:
        await storage.upload(key, make_png(_MIN_DIMENSION, _MIN_DIMENSION), "image/png")
    await job_repo.save(make_job("job-1", keys))

    result = await _build(storage, job_repo).ainvoke(_state(keys))

    assert result["validation_passed"] is True


async def test_intake_gate_fails_too_few_photos() -> None:
    storage, job_repo = StorageFake(), JobRepoFake()
    keys = [f"jobs/job-1/p{i}" for i in range(settings.photo_min_count - 1)]
    for key in keys:
        await storage.upload(key, make_jpeg(), "image/jpeg")
    await job_repo.save(make_job("job-1", keys))

    result = await _build(storage, job_repo).ainvoke(_state(keys))

    assert result["validation_passed"] is False
    assert any(str(settings.photo_min_count - 1) in e for e in result["validation_errors"])


async def test_intake_gate_fails_too_many_photos() -> None:
    storage, job_repo = StorageFake(), JobRepoFake()
    keys = [f"jobs/job-1/p{i}" for i in range(settings.photo_max_count + 1)]
    for key in keys:
        await storage.upload(key, make_jpeg(), "image/jpeg")
    await job_repo.save(make_job("job-1", keys))

    result = await _build(storage, job_repo).ainvoke(_state(keys))

    assert result["validation_passed"] is False
    assert any(str(settings.photo_max_count + 1) in e for e in result["validation_errors"])


async def test_intake_gate_fails_small_dimensions() -> None:
    storage, job_repo = StorageFake(), JobRepoFake()
    keys = [f"jobs/job-1/p{i}" for i in range(settings.photo_min_count)]
    small = _MIN_DIMENSION - 1
    for i, key in enumerate(keys):
        data = make_jpeg(small, small) if i == 0 else make_jpeg(_MIN_DIMENSION, _MIN_DIMENSION)
        await storage.upload(key, data, "image/jpeg")
    await job_repo.save(make_job("job-1", keys))

    result = await _build(storage, job_repo).ainvoke(_state(keys))

    assert result["validation_passed"] is False
    assert any(str(small) in e for e in result["validation_errors"])


async def test_intake_gate_fails_bad_magic_bytes() -> None:
    storage, job_repo = StorageFake(), JobRepoFake()
    keys = [f"jobs/job-1/p{i}" for i in range(settings.photo_min_count)]
    for i, key in enumerate(keys):
        data = b"not-an-image-data-xx" if i == 0 else make_jpeg()
        await storage.upload(key, data, "image/jpeg")
    await job_repo.save(make_job("job-1", keys))

    result = await _build(storage, job_repo).ainvoke(_state(keys))

    assert result["validation_passed"] is False
    assert any("Invalid image format" in e for e in result["validation_errors"])


async def test_intake_gate_tags_photo_roles() -> None:
    storage, job_repo = StorageFake(), JobRepoFake()
    keys = await _valid_storage(storage)
    await job_repo.save(make_job("job-1", keys))

    result = await _build(storage, job_repo).ainvoke(_state(keys))

    assert result["photo_roles"][keys[0]] == PhotoRole.close_up


async def test_intake_gate_rejects_junk_photos() -> None:
    """A photo set the vision model deems not a building/defect submission is rejected before
    any strong-model call — this is the cost-control junk-photo filter, not mechanical
    validation (which passes here — well-formed JPEGs of the right size)."""
    storage, job_repo = StorageFake(), JobRepoFake()
    keys = await _valid_storage(storage)
    await job_repo.save(make_job("job-1", keys))

    stub = VisionLLMStub(reject_intake=True, rejection_reason="Looks like a selfie")

    result = await _build(storage, job_repo, stub).ainvoke(_state(keys))

    assert result["validation_passed"] is False
    assert any("Looks like a selfie" in e for e in result["validation_errors"])
    assert result["defect_classification"] is None


# ---------------------------------------------------------------------------
# ai_assessment node
# ---------------------------------------------------------------------------


async def test_ai_assessment_sets_defect_type_on_job() -> None:
    storage, job_repo = StorageFake(), JobRepoFake()
    keys = await _valid_storage(storage)
    await job_repo.save(make_job("job-1", keys))

    await _build(storage, job_repo).ainvoke(_state(keys))

    persisted = [u for u in job_repo.status_updates if "defect_type" in u]
    assert len(persisted) == 1
    assert persisted[0]["defect_type"] == "crack"


async def test_ai_assessment_returns_classification_in_state() -> None:
    storage, job_repo = StorageFake(), JobRepoFake()
    keys = await _valid_storage(storage)
    await job_repo.save(make_job("job-1", keys))

    result = await _build(storage, job_repo).ainvoke(_state(keys))

    classification = result["defect_classification"]
    assert classification is not None
    assert classification.defect_type == "crack"
    assert classification.severity == "medium"
    assert classification.confidence == 0.8
    assert classification.verification_items


async def test_ai_assessment_writes_summary_in_customer_language() -> None:
    storage, job_repo = StorageFake(), JobRepoFake()
    keys = await _valid_storage(storage)
    await job_repo.save(make_job("job-1", keys))

    result = await _build(storage, job_repo).ainvoke(_state(keys, customer_language="de"))

    assert result["defect_classification"].summary == "[de] Hairline crack summary."


async def test_ai_assessment_verification_items_carry_kind() -> None:
    """verification_items must be typed (customer_question | photo_request | expert_only_check)
    — see AI_ASSESSMENT_REWORK.md "Typed verification items"; downstream consumers (the
    customer reply UI, the expert report) branch on `kind`, not just `text`."""
    storage, job_repo = StorageFake(), JobRepoFake()
    keys = await _valid_storage(storage)
    await job_repo.save(make_job("job-1", keys))

    result = await _build(storage, job_repo).ainvoke(_state(keys))

    items = result["verification_items"]
    assert items
    assert items[0]["kind"] == "expert_only_check"
    assert "text" in items[0]


async def test_ai_assessment_skipped_when_validation_fails() -> None:
    storage, job_repo = StorageFake(), JobRepoFake()
    keys = [f"jobs/job-1/p{i}" for i in range(settings.photo_min_count - 1)]
    for key in keys:
        await storage.upload(key, make_jpeg(), "image/jpeg")
    await job_repo.save(make_job("job-1", keys))

    result = await _build(storage, job_repo).ainvoke(_state(keys))

    assert result["defect_classification"] is None
    assert not any("defect_type" in u for u in job_repo.status_updates)


# ---------------------------------------------------------------------------
# await_customer_answers — clarification-loop pause (customer_after_questions=1 default)
# ---------------------------------------------------------------------------


async def test_pauses_for_customer_input_after_first_assessment() -> None:
    storage, job_repo = StorageFake(), JobRepoFake()
    keys = await _valid_storage(storage)
    await job_repo.save(make_job("job-1", keys))

    result = await _build(storage, job_repo).ainvoke(_state(keys))

    assert job_repo._jobs["job-1"].status == JobStatus.awaiting_customer_input
    assert result["report_key"] is None


async def test_no_second_assessment_call_before_customer_responds() -> None:
    """Regression test for the point of the whole loop design: declining to reply must not
    trigger a second (paid) ai_assessment call — see AI_ASSESSMENT_REWORK.md verification #2."""
    storage, job_repo = StorageFake(), JobRepoFake()
    keys = await _valid_storage(storage)
    await job_repo.save(make_job("job-1", keys))

    result = await _build(storage, job_repo).ainvoke(_state(keys))

    persisted = [u for u in job_repo.status_updates if "defect_type" in u]
    assert len(persisted) == 1  # exactly one ai_assessment call, not two
    assert result["api_call_count"] == 2  # intake_gate + ai_assessment


async def test_resume_graph_closes_loop_and_reaches_report_generator() -> None:
    """With qa_history already at the round cap, the resume graph (entered directly at
    ai_assessment — what RespondToJob's reply path uses) proceeds straight through to
    report_generator instead of pausing again."""
    storage, job_repo = StorageFake(), JobRepoFake()
    keys = await _valid_storage(storage)
    await job_repo.save(make_job("job-1", keys))

    state = _state(keys, qa_history=[{"round": 0, "customer_reply": "It's on the north wall."}])
    result = await _build_resume(storage, job_repo).ainvoke(state)

    assert result["report_key"] == "jobs/job-1/report.pdf"
    assert job_repo._jobs["job-1"].status == JobStatus.complete


# ---------------------------------------------------------------------------
# report_generator node (via the resume graph, loop already closed)
# ---------------------------------------------------------------------------


async def test_report_generator_uploads_pdf() -> None:
    storage, job_repo = StorageFake(), JobRepoFake()
    keys = await _valid_storage(storage)
    await job_repo.save(make_job("job-1", keys))

    state = _state(keys, qa_history=[{"round": 0, "customer_reply": "x"}])
    await _build_resume(storage, job_repo).ainvoke(state)

    assert "jobs/job-1/report.pdf" in storage._data
    assert storage._data["jobs/job-1/report.pdf"].startswith(b"%PDF-stub")


async def test_report_generator_sets_state_fields() -> None:
    storage, job_repo = StorageFake(), JobRepoFake()
    keys = await _valid_storage(storage)
    await job_repo.save(make_job("job-1", keys))

    state = _state(keys, qa_history=[{"round": 0, "customer_reply": "x"}])
    result = await _build_resume(storage, job_repo).ainvoke(state)

    assert result["report_key"] == "jobs/job-1/report.pdf"
    assert result["report_url"] == "https://fake/jobs/job-1/report.pdf"
    assert result["severity"] == "medium"


async def test_report_generator_persists_severity_and_report_key() -> None:
    storage, job_repo = StorageFake(), JobRepoFake()
    keys = await _valid_storage(storage)
    await job_repo.save(make_job("job-1", keys))

    state = _state(keys, qa_history=[{"round": 0, "customer_reply": "x"}])
    await _build_resume(storage, job_repo).ainvoke(state)

    persisted = [u for u in job_repo.status_updates if "report_key" in u]
    assert len(persisted) == 1
    assert persisted[0]["severity"] == "medium"
    assert persisted[0]["report_key"] == "jobs/job-1/report.pdf"
    assert persisted[0]["status"] == JobStatus.complete


async def test_report_generator_renders_ai_assessment_summary_directly() -> None:
    """report_generator no longer runs a second (synthesize) LLM call — it renders whatever
    ai_assessment already produced, verbatim."""
    storage, job_repo = StorageFake(), JobRepoFake()
    keys = await _valid_storage(storage)
    await job_repo.save(make_job("job-1", keys))

    state = _state(keys, qa_history=[{"round": 0, "customer_reply": "x"}])
    await _build_resume(storage, job_repo).ainvoke(state)

    persisted = [u for u in job_repo.status_updates if "report_key" in u]
    assert len(persisted) == 1
    assert persisted[0]["summary"] == "Hairline crack summary."


# ---------------------------------------------------------------------------
# Anthropic API call cap — independent hard ceiling (see call_budget.py)
# ---------------------------------------------------------------------------


async def test_call_budget_exceeded_fails_job_before_intake_vision_call() -> None:
    storage, job_repo = StorageFake(), JobRepoFake()
    keys = await _valid_storage(storage)
    await job_repo.save(make_job("job-1", keys))

    state = _state(keys, api_call_count=settings.anthropic_max_calls_per_job)

    with pytest.raises(CallBudgetExceededError):
        await _build(storage, job_repo).ainvoke(state)

    assert job_repo._jobs["job-1"].status == JobStatus.failed
    assert job_repo._jobs["job-1"].error == "api_call_limit_exceeded"


async def test_call_budget_exceeded_fails_job_before_ai_assessment_call() -> None:
    storage, job_repo = StorageFake(), JobRepoFake()
    keys = await _valid_storage(storage)
    await job_repo.save(make_job("job-1", keys))

    # One call under the ceiling — intake_gate's own call brings it to the ceiling, so
    # ai_assessment is the one that trips it.
    state = _state(keys, api_call_count=settings.anthropic_max_calls_per_job - 1)

    with pytest.raises(CallBudgetExceededError):
        await _build(storage, job_repo).ainvoke(state)

    assert job_repo._jobs["job-1"].status == JobStatus.failed
    assert job_repo._jobs["job-1"].error == "api_call_limit_exceeded"


async def test_ai_assessment_summary_written_to_state() -> None:
    storage, job_repo = StorageFake(), JobRepoFake()
    keys = await _valid_storage(storage)
    await job_repo.save(make_job("job-1", keys))

    result = await _build(storage, job_repo).ainvoke(_state(keys))

    assert result["defect_classification"].summary == "Hairline crack summary."
