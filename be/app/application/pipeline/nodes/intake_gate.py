import io
from typing import Any

from PIL import Image

from app.core.config import settings
from app.domain.job import JobStatus
from app.domain.ports.job_repo import JobRepository
from app.domain.ports.storage import StoragePort
from app.domain.ports.vision_llm import VisionLLMPort

from ..call_budget import guard_call_budget
from ..state import AssessmentState

_MIN_DIMENSION = 500


def _valid_magic(data: bytes) -> bool:
    if data[:3] == b"\xff\xd8\xff":
        return True
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return True
    return (
        len(data) >= 12
        and data[4:8] == b"ftyp"
        and data[8:12] in (b"heic", b"heix", b"mif1", b"msf1")
    )


def intake_gate(
    storage: StoragePort, job_repo: JobRepository, vision_llm: VisionLLMPort
) -> Any:  # LangGraph node callable
    async def _node(state: AssessmentState) -> dict[str, Any]:
        await job_repo.update_status(state["job_id"], JobStatus.processing)

        errors: list[str] = []
        keys = state["photo_keys"]

        if not (settings.photo_min_count <= len(keys) <= settings.photo_max_count):
            errors.append(
                f"Expected {settings.photo_min_count}–{settings.photo_max_count} photos, got {len(keys)}"
            )

        for key in keys:
            data = await storage.download(key)

            if not _valid_magic(data):
                errors.append(f"Invalid image format: {key}")
                continue

            try:
                with Image.open(io.BytesIO(data)) as img:
                    w, h = img.size
                    if w < _MIN_DIMENSION or h < _MIN_DIMENSION:
                        errors.append(
                            f"Image too small ({w}×{h}), minimum "
                            f"{_MIN_DIMENSION}×{_MIN_DIMENSION}: {key}"
                        )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Could not read image {key}: {exc}")

        if errors:
            return {"validation_passed": False, "validation_errors": errors, "photo_roles": {}}

        await guard_call_budget(job_repo, state["job_id"], state["api_call_count"])
        result = await vision_llm.validate_intake(keys)
        new_call_count = state["api_call_count"] + 1

        if not result.accepted:
            errors.append(result.rejection_reason or "Photos rejected at intake")
            return {
                "validation_passed": False,
                "validation_errors": errors,
                "photo_roles": result.photo_roles,
                "api_call_count": new_call_count,
            }

        return {
            "validation_passed": True,
            "validation_errors": [],
            "photo_roles": result.photo_roles,
            "api_call_count": new_call_count,
        }

    return _node
