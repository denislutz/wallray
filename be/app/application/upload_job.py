import io
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import UploadFile
from PIL import Image

from app.core.config import settings
from app.domain.job import Job, JobStatus, Photo, PhotoRole
from app.domain.ports.job_repo import JobRepository
from app.domain.ports.storage import StoragePort
from app.domain.ports.user_repo import UserRepository
from app.domain.user import UserRole

_ALLOWED_TYPES = frozenset(
    {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/heic", "image/heif"}
)

# Filename-based role hint — stand-in for a future guided-upload UI field.
# Resolves once, here, into Photo.role; downstream code only ever reads
# the resolved role and never re-derives it from a filename.
_ROLE_FILENAME_HINTS: dict[PhotoRole, tuple[str, ...]] = {
    PhotoRole.close_up: ("close",),
    PhotoRole.context: ("context", "wide", "overview"),
    PhotoRole.repeat_location: ("repeat", "pattern", "similar"),
}


def _resolve_role_from_filename(filename: str) -> PhotoRole | None:
    stem = filename.rsplit(".", 1)[0].lower()
    for role, hints in _ROLE_FILENAME_HINTS.items():
        if any(hint in stem for hint in hints):
            return role
    return None


_DERIVED_NAME_MAX_CHARS = 40


def _derive_name(description: str | None) -> str | None:
    """Falls back to the first few words of the description when the customer leaves the
    report name blank — a title beats an empty field in the report list."""
    stripped = (description or "").strip()
    if not stripped:
        return None
    if len(stripped) <= _DERIVED_NAME_MAX_CHARS:
        return stripped
    truncated = stripped[:_DERIVED_NAME_MAX_CHARS]
    last_space = truncated.rfind(" ")
    if last_space > 0:
        truncated = truncated[:last_space]
    return f"{truncated}…"


def _resolve_name(name: str | None, description: str | None) -> str | None:
    stripped = (name or "").strip()
    return stripped or _derive_name(description)


class FreeTierLimitError(Exception):
    def __init__(self, limit: int) -> None:
        super().__init__(f"Free tier limit of {limit} reports reached")
        self.limit = limit


class ValidationError(Exception):
    pass


def _check_magic_bytes(data: bytes, filename: str) -> None:
    if data[:3] == b"\xff\xd8\xff":
        return
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return
    if (
        len(data) >= 12
        and data[4:8] == b"ftyp"
        and data[8:12] in (b"heic", b"heix", b"mif1", b"msf1")
    ):
        return
    raise ValidationError(f"File content does not match a supported image format: {filename}")


def _downscale(data: bytes, target_factor: float = 0.5) -> tuple[bytes, str]:
    base: Image.Image = Image.open(io.BytesIO(data))
    if base.mode not in ("RGB", "RGBA"):
        base = base.convert("RGB")
    w, h = base.size
    new_w = max(1, round(w * target_factor))
    new_h = max(1, round(h * target_factor))
    resized: Image.Image = base.resize((new_w, new_h), Image.Resampling.LANCZOS)
    if resized.mode == "RGBA":
        resized = resized.convert("RGB")
    buf = io.BytesIO()
    resized.save(buf, format="JPEG", quality=85)
    return buf.getvalue(), "image/jpeg"


def _make_thumbnail(data: bytes, max_px: int = 400) -> bytes:
    base: Image.Image = Image.open(io.BytesIO(data))
    if base.mode not in ("RGB", "RGBA"):
        base = base.convert("RGB")
    w, h = base.size
    result: Image.Image
    if w > max_px:
        new_h = max(1, round(max_px * h / w))
        result = base.resize((max_px, new_h), Image.Resampling.LANCZOS)
    else:
        result = base
    if result.mode == "RGBA":
        result = result.convert("RGB")
    buf = io.BytesIO()
    result.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


class UploadJob:
    def __init__(
        self,
        storage: StoragePort,
        job_repo: JobRepository,
        user_repo: UserRepository,
    ) -> None:
        self._storage = storage
        self._job_repo = job_repo
        self._user_repo = user_repo

    async def execute(
        self,
        user_id: str,
        files: list[UploadFile],
        description: str | None,
        name: str | None = None,
        language: str = "en",
    ) -> str:
        user = await self._user_repo.get(user_id)
        if user is not None:
            limit = (
                settings.free_tier_limit_expert
                if user.role == UserRole.expert_review
                else settings.free_tier_limit
            )
            if user.report_count >= limit:
                raise FreeTierLimitError(limit)

        if not 1 <= len(files) <= 10:
            raise ValidationError(f"Submit 1–10 photos (got {len(files)})")

        job_id = str(uuid4())
        photos: list[Photo] = []

        for file in files:
            content_type = file.content_type or ""
            if content_type not in _ALLOWED_TYPES:
                raise ValidationError(f"Unsupported file type: {content_type!r}")

            data = await file.read()

            if len(data) > settings.photo_max_size_mb * 1024 * 1024:
                raise ValidationError(
                    f"File exceeds {settings.photo_max_size_mb} MB limit: {file.filename!r}"
                )

            _check_magic_bytes(data, file.filename or "")

            if len(data) > settings.photo_resize_threshold_mb * 1024 * 1024:
                data, content_type = _downscale(data, target_factor=0.5)

            key = f"jobs/{job_id}/{uuid4()}"
            await self._storage.upload(key, data, content_type)

            thumb_bytes = _make_thumbnail(data, max_px=400)
            thumb_key = f"jobs/{job_id}/thumbs/{uuid4()}"
            await self._storage.upload(thumb_key, thumb_bytes, "image/jpeg")

            role = _resolve_role_from_filename(file.filename or "")
            photos.append(Photo(key=key, content_type=content_type, thumb_key=thumb_key, role=role))

        job = Job(
            id=job_id,
            user_id=user_id,
            status=JobStatus.pending,
            photos=photos,
            description=description,
            created_at=datetime.now(UTC),
            thumbnail_key=photos[0].thumb_key or photos[0].key,
            name=_resolve_name(name, description),
            customer_language=language,
        )
        await self._job_repo.save(job)
        return job_id
