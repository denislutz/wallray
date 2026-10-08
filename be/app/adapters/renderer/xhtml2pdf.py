from __future__ import annotations

import asyncio
import base64
import io
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import markdown
from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup, escape
from PIL import Image

from app.core.config import settings
from app.core.i18n import load_catalog, translator
from app.domain.job import DefectClassification, Job

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=True)

_LOCALES_DIR = Path(__file__).parent / "locales"

_DISCLAIMER_KEY = (
    "AI-generated assessment, not a professional structural or building survey. Obtain a "
    "qualified professional inspection before making repair, legal, or financial decisions."
)

_FONTS_DIR = Path(__file__).parent / "fonts"
# xhtml2pdf/reportlab does no font substitution for missing glyphs (unlike the WeasyPrint/Pango
# renderer this replaced) — without an embedded Unicode font, Cyrillic/Greek text renders as
# black .notdef boxes. DejaVu Sans covers Latin/Cyrillic/Greek in one file.
FONT_REGULAR = str(_FONTS_DIR / "DejaVuSans.ttf")
FONT_BOLD = str(_FONTS_DIR / "DejaVuSans-Bold.ttf")


def _render_markdown(text: str) -> Markup:
    # Escape first so raw HTML in LLM/customer/expert free text can't inject into the PDF —
    # markdown syntax survives escaping, so this only affects literal HTML, not formatting.
    return Markup(markdown.markdown(str(escape(text))))


def _defect_type_label(catalog: dict[str, str], defect_type: str) -> str:
    # defect_type is a free-form identifier the vision LLM assigns — only the common ones
    # have a catalog entry, anything else falls back to a humanized version of the raw slug.
    return catalog.get(f"report_defect_type_{defect_type}") or defect_type.replace("_", " ").title()


def _severity_label(catalog: dict[str, str], severity: str) -> str:
    return catalog.get(f"report_severity_{severity}") or severity.replace("_", " ").title()


def _shrink_for_embedding(data: bytes, max_bytes: int) -> bytes:
    """Downscale a photo for PDF embedding only — the stored original is untouched.

    Repeatedly halves linear dimensions until under max_bytes, so a report with several
    photos doesn't balloon into a multi-tens-of-MB PDF.
    """
    if len(data) <= max_bytes:
        return data

    image: Image.Image = Image.open(io.BytesIO(data))
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGB")
    if image.mode == "RGBA":
        image = image.convert("RGB")

    current = data
    width, height = image.size
    while len(current) > max_bytes and min(width, height) > 100:
        width, height = max(1, round(width * 0.7)), max(1, round(height * 0.7))
        image = image.resize((width, height), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=85)
        current = buf.getvalue()
    return current


class Xhtml2pdfAdapter:
    async def render(
        self,
        job: Job,
        classification: DefectClassification,
        photo_data: list[bytes],
        expert_notes: str | None = None,
        summary_override: str | None = None,
        locale: str | None = None,
    ) -> bytes:
        resolved_locale = locale or job.customer_language
        catalog = load_catalog(_LOCALES_DIR, resolved_locale)
        t = translator(_LOCALES_DIR, resolved_locale)

        summary = summary_override or classification.summary or ""
        max_bytes = int(settings.report_photo_max_size_mb * 1024 * 1024)
        photo_b64 = [
            base64.b64encode(_shrink_for_embedding(d, max_bytes)).decode() for d in photo_data
        ]
        html = _env.get_template("report.html").render(
            job_id=job.id,
            name=job.name,
            created_at=job.created_at.strftime("%Y-%m-%d %H:%M UTC"),
            defect_type=_defect_type_label(catalog, classification.defect_type),
            severity=classification.severity,
            severity_label=_severity_label(catalog, classification.severity),
            summary=_render_markdown(summary) if summary else "",
            description=job.description,
            expert_note_localized=_render_markdown(classification.expert_note_localized)
            if classification.expert_note_localized
            else None,
            generated_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
            photo_b64=photo_b64,
            font_regular=FONT_REGULAR,
            font_bold=FONT_BOLD,
            legal_url=f"{settings.marketing_base_url}/legal",
            report_title=t("WallRay Defect Assessment Report"),
            job_label=t("Job"),
            section_summary=t("Assessment Summary"),
            label_defect_type=t("Defect type"),
            label_severity=t("Severity"),
            section_description=t("Submitted Description"),
            section_photos=t("Submitted Photos"),
            section_expert_note=t("Expert Note"),
            disclaimer_text=t(_DISCLAIMER_KEY),
            disclaimer_full_label=t("Full disclaimer:"),
            generated_by_label=t("Generated by WallRay"),
        )
        pdf_bytes: bytes = await asyncio.to_thread(_render_pdf, html)
        return pdf_bytes


def _render_pdf(html: str) -> bytes:
    from xhtml2pdf import pisa  # pure-Python, no system deps

    buf = BytesIO()
    result = pisa.CreatePDF(html, dest=buf)
    if result.err:
        raise RuntimeError(f"xhtml2pdf error code {result.err}")
    return buf.getvalue()
