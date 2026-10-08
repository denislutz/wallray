import io
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import jwt
from PIL import Image

from app.core.config import settings
from app.domain.job import DefectClassification, IntakeResult, Job, JobStatus, Photo, PhotoRole
from app.domain.user import User, UserRole

# Fixed UUID used as the default test user's JWT sub.
# Must be a valid UUID — pg_user_repo.get() parses it with uuid.UUID().
TEST_USER_ID = "00000000-0000-0000-0000-000000000001"


def auth_token(user_id: str = TEST_USER_ID) -> str:
    token: str = jwt.encode(
        {
            "sub": user_id,
            "email": f"test-{user_id}@test.local",
            "exp": datetime.now(UTC) + timedelta(hours=1),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return token


def auth_headers(user_id: str = TEST_USER_ID) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth_token(user_id)}"}


def make_jpeg(width: int = 600, height: int = 600) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=(128, 128, 128)).save(buf, format="JPEG")
    return buf.getvalue()


def make_png(width: int = 600, height: int = 600) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=(64, 64, 64)).save(buf, format="PNG")
    return buf.getvalue()


def make_webp(width: int = 600, height: int = 600) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=(100, 100, 100)).save(buf, format="WEBP")
    return buf.getvalue()


def expired_token(user_id: str = TEST_USER_ID) -> str:
    token: str = jwt.encode(
        {"sub": user_id, "exp": datetime.now(UTC) - timedelta(hours=1)},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return token


def make_job(
    job_id: str,
    photo_keys: list[str],
    user_id: str = "user-1",
    request_expert_review: bool = False,
    customer_language: str = "en",
) -> Job:
    return Job(
        id=job_id,
        user_id=user_id,
        status=JobStatus.pending,
        photos=[Photo(key=k, content_type="image/jpeg") for k in photo_keys],
        description=None,
        created_at=datetime.now(UTC),
        thumbnail_key=photo_keys[0] if photo_keys else None,
        request_expert_review=request_expert_review,
        customer_language=customer_language,
    )


class StorageFake:
    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}

    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        self._data[key] = data
        return key

    async def download(self, key: str) -> bytes:
        return self._data[key]

    async def signed_url(self, key: str, expires: int = 3600) -> str:
        return f"https://fake/{key}"


class EmailFake:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []
        self.expert_requests: list[dict[str, Any]] = []
        self.new_user_notifications: list[dict[str, str]] = []

    async def send_report(
        self, to: str, job_id: str, report_url: str, app_report_url: str = "", locale: str = "en"
    ) -> None:
        self.sent.append(
            {"to": to, "job_id": job_id, "report_url": report_url, "app_report_url": app_report_url}
        )

    async def send_expert_review_request(
        self,
        to: str,
        job_id: str,
        review_url: str,
        defect_type: str,
        severity: str,
        assessment_summary: str | None = None,
        locale: str = "en",
    ) -> None:
        self.expert_requests.append(
            {
                "to": to,
                "job_id": job_id,
                "review_url": review_url,
                "assessment_summary": assessment_summary,
            }
        )

    async def send_new_user_notification(
        self, to: str, user_email: str, role: str, locale: str = "en"
    ) -> None:
        self.new_user_notifications.append({"to": to, "user_email": user_email, "role": role})


class UserRepoFake:
    def __init__(self) -> None:
        self.increments: list[str] = []
        self._users: dict[str, User] = {}

    async def _set_user(self, user: User) -> None:
        self._users[user.id] = user

    async def upsert(self, user: User) -> User:
        self._users[user.id] = user
        return user

    async def get(self, user_id: str) -> User | None:
        return self._users.get(user_id)

    async def increment_count(self, user_id: str) -> None:
        self.increments.append(user_id)

    async def update_language(self, user_id: str, language: str) -> None:
        user = self._users.get(user_id)
        if user is not None:
            user.preferred_language = language

    async def get_or_create_by_email(self, email: str, role: UserRole) -> User:
        for u in self._users.values():
            if u.email == email:
                return u
        user = User(id=f"expert-{email}", email=email, role=role)
        self._users[user.id] = user
        return user

    async def get_by_emails(self, emails: list[str]) -> list[User]:
        return [u for u in self._users.values() if u.email in emails]


class VisionLLMStub:
    def __init__(
        self, reject_intake: bool = False, rejection_reason: str | None = "Not a defect photo"
    ) -> None:
        self._reject_intake = reject_intake
        self._rejection_reason = rejection_reason

    async def validate_intake(self, photo_keys: list[str]) -> IntakeResult:
        if self._reject_intake:
            return IntakeResult(
                accepted=False, rejection_reason=self._rejection_reason, photo_roles={}
            )
        roles = {
            key: (PhotoRole.close_up if i == 0 else PhotoRole.context)
            for i, key in enumerate(photo_keys)
        }
        return IntakeResult(accepted=True, rejection_reason=None, photo_roles=roles)

    async def translate(self, text: str, target_language: str) -> str:
        return f"[{target_language}] {text}"

    async def assess(
        self,
        photo_keys: list[str],
        context_signals: dict[str, Any],
        prior_summary: str | None = None,
        expert_notes: str | None = None,
        customer_language: str = "en",
        expert_language: str | None = None,
    ) -> DefectClassification:
        if expert_notes is not None:
            summary = f"Synthesized: {expert_notes}"
            summary_expert = (
                f"[{expert_language}] {summary}"
                if expert_language and expert_language != customer_language
                else None
            )
            expert_note_localized = (
                f"[{customer_language}] {expert_notes}" if expert_notes else None
            )
            return DefectClassification(
                defect_type="crack",
                severity="high",
                summary=summary,
                summary_expert=summary_expert,
                expert_note_localized=expert_note_localized,
            )

        # summary must vary with customer_language — that's the whole point of assess()
        # writing customer-facing prose natively instead of translating on read.
        base = "Hairline crack summary." if not prior_summary else f"{prior_summary} Extended."
        summary = base if customer_language == "en" else f"[{customer_language}] {base}"
        return DefectClassification(
            defect_type="crack",
            severity="medium",
            summary=summary,
            confidence=0.8,
            verification_items=[
                {"text": "Check moisture at three heights", "kind": "expert_only_check"}
            ],
        )


class RendererStub:
    async def render(
        self,
        job: Any,
        classification: DefectClassification,
        photo_data: list[bytes],
        expert_notes: str | None = None,
        summary_override: str | None = None,
        locale: str | None = None,
    ) -> bytes:
        marker = summary_override or "default"
        return f"%PDF-stub-{marker}".encode()


class JobRepoFake:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self.status_updates: list[dict[str, Any]] = []

    async def save(self, job: Job) -> None:
        self._jobs[job.id] = job

    async def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    async def list_by_user(self, user_id: str) -> list[Job]:
        return [j for j in self._jobs.values() if j.user_id == user_id]

    async def list_by_assigned_expert(self, expert_id: str, status: JobStatus) -> list[Job]:
        return [
            j
            for j in self._jobs.values()
            if j.assigned_expert_id == expert_id and j.status == status
        ]

    async def list_all_by_assigned_expert(self, expert_id: str) -> list[Job]:
        return [j for j in self._jobs.values() if j.assigned_expert_id == expert_id]

    async def update_status(self, job_id: str, status: JobStatus, **fields: Any) -> None:
        self.status_updates.append({"job_id": job_id, "status": status, **fields})
        job = self._jobs.get(job_id)
        if job is not None:
            job.status = status
            for k, v in fields.items():
                setattr(job, k, v)
