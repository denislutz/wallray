import asyncio
import functools
import logging
from pathlib import Path
from typing import Any, cast

import resend as resend_sdk
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import settings
from app.core.i18n import translator as _translator

logger = logging.getLogger(__name__)

_LOCALES_DIR = Path(__file__).parent / "locales"
_TEMPLATES_DIR = Path(__file__).parent / "templates"

_env = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIR),
    autoescape=select_autoescape(["html"]),
)


def _render(template_name: str, locale: str = "en", **ctx: Any) -> str:
    return _env.get_template(template_name).render(_=_translator(_LOCALES_DIR, locale), **ctx)


class ResendAdapter:
    def __init__(self, api_key: str, from_address: str) -> None:
        self._api_key = api_key
        self._from_address = from_address

    async def _send(self, params: dict[str, Any]) -> None:
        if not self._api_key:
            logger.info("Resend API key not configured — skipping email to %s", params.get("to"))
            return

        def _do_send() -> None:
            resend_sdk.api_key = self._api_key
            resend_sdk.Emails.send(cast(Any, params))

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, functools.partial(_do_send))

    async def send_report(
        self,
        to: str,
        job_id: str,
        report_url: str,
        app_report_url: str,
        locale: str = "en",
    ) -> None:
        if not to:
            logger.warning("No recipient email for job %s — skipping email", job_id)
            return
        t = _translator(_LOCALES_DIR, locale)
        await self._send(
            {
                "from": self._from_address,
                "to": [to],
                "subject": t("Your WallRay Assessment Report is Ready"),
                "html": _render(
                    "report.html",
                    locale=locale,
                    job_id=job_id,
                    report_url=report_url,
                    app_report_url=app_report_url,
                    legal_url=f"{settings.marketing_base_url}/legal",
                ),
            }
        )
        logger.info("Report email sent to %s for job %s", to, job_id)

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
        if not to:
            logger.warning(
                "No expert email configured — skipping review request for job %s", job_id
            )
            return
        t = _translator(_LOCALES_DIR, locale)
        await self._send(
            {
                "from": self._from_address,
                "to": [to],
                "subject": t("WallRay — Job ready for expert review"),
                "html": _render(
                    "expert_review.html",
                    locale=locale,
                    job_id=job_id,
                    review_url=review_url,
                    defect_type=defect_type,
                    severity=severity,
                    assessment_summary=assessment_summary,
                ),
            }
        )
        logger.info("Expert review request sent to %s for job %s", to, job_id)

    async def send_new_user_notification(
        self, to: str, user_email: str, role: str, locale: str = "en"
    ) -> None:
        if not to:
            logger.info("No new-user notification recipient configured — skipping")
            return
        t = _translator(_LOCALES_DIR, locale)
        await self._send(
            {
                "from": self._from_address,
                "to": [to],
                "subject": t("WallRay — New user registered"),
                "html": _render(
                    "new_user.html",
                    locale=locale,
                    user_email=user_email,
                    role=role,
                ),
            }
        )
        logger.info("New-user notification sent to %s for %s", to, user_email)
