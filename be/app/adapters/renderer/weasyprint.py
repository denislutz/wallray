# DISABLED — WeasyPrint requires native system libs (Pango, GLib, Cairo) that
# must be apt-get installed in Docker, bloating the image and breaking most PaaS
# deployments. Use Xhtml2pdfAdapter instead (pure Python, no system deps).
# Keep this file as a reference in case high-fidelity CSS rendering is needed later.

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from app.core.config import settings
from app.domain.job import DefectClassification, Job

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=True)


class WeasyPrintAdapter:
    async def render(self, job: Job, classification: DefectClassification) -> bytes:
        html = _env.get_template("report.html").render(
            job_id=job.id,
            created_at=job.created_at.strftime("%Y-%m-%d %H:%M UTC"),
            defect_type=classification.defect_type.replace("_", " ").title(),
            severity=classification.severity,
            notes=classification.summary,
            description=job.description,
            generated_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
            legal_url=f"{settings.marketing_base_url}/legal",
        )
        pdf_bytes: bytes = await asyncio.to_thread(_render_pdf, html)
        return pdf_bytes


def _render_pdf(html: str) -> bytes:
    import weasyprint  # lazy: native Pango/GLib libs only needed at render time

    result: bytes = weasyprint.HTML(string=html).write_pdf()
    return result
