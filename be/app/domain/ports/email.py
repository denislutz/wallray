from typing import Protocol


class EmailPort(Protocol):
    async def send_report(
        self, to: str, job_id: str, report_url: str, app_report_url: str, locale: str = "en"
    ) -> None: ...

    async def send_expert_review_request(
        self,
        to: str,
        job_id: str,
        review_url: str,
        defect_type: str,
        severity: str,
        assessment_summary: str | None = None,
        locale: str = "en",
    ) -> None: ...

    async def send_new_user_notification(
        self, to: str, user_email: str, role: str, locale: str = "en"
    ) -> None: ...
