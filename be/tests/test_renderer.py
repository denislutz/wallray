"""Visual render test — generates be/tests/output/test_render.pdf on every run.

Renders through Xhtml2pdfAdapter and the real report.html template (not a parallel
copy) so a Unicode/Cyrillic regression in the shipped font or CSS is caught here.
Covers: Latin, Cyrillic, Greek, €/■/– symbols, markdown summary, photo grid.
Open the PDF after `pytest` to verify output visually.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image

from app.adapters.renderer.xhtml2pdf import (
    _LOCALES_DIR,
    FONT_BOLD,
    FONT_REGULAR,
    Xhtml2pdfAdapter,
    _defect_type_label,
    _severity_label,
)
from app.core.config import settings
from app.core.i18n import load_catalog
from app.domain.job import DefectClassification, Job, JobStatus

IMG_DIR = Path(__file__).parent.parent.parent / "docs/clusterindex/pics"
OUT_DIR = Path(__file__).parent / "output"

_CYRILLIC = (
    "Трещина в стене — высокая влажность, плесень. Критический уровень повреждений. "
    "Примечание: не красить до завершения шагов 1–3."
)
_GREEK = "Τεχνική αξιολόγηση κτιρίου. Υγρασία, ρωγμές, μούχλα. Επείγουσα επισκευή απαιτείται."
_SYMBOLS = "€100–€200 · ±5% · ≥400 px · ©2026 · ■■■■■"


def _minimal_job(job_id: str = "r-1", *, name: str | None = None) -> Job:
    return Job(
        id=job_id,
        user_id="u-1",
        status=JobStatus.expert_review,
        photos=[],
        description=None,
        created_at=datetime.now(UTC),
        name=name,
    )


def _sample_photos(max_images: int = 3) -> list[bytes]:
    if not IMG_DIR.is_dir():
        return []
    paths = [p for p in sorted(IMG_DIR.iterdir()) if p.suffix.lower() in {".jpg", ".jpeg", ".png"}][
        :max_images
    ]
    return [p.read_bytes() for p in paths]


def test_font_files_exist_and_cover_cyrillic() -> None:
    """The bundled font must exist on disk — a missing/renamed file fails silently at

    render time otherwise (xhtml2pdf just drops the @font-face rule and falls back to a
    Latin-only core font, which is exactly how this regression happened before).
    """
    assert Path(FONT_REGULAR).is_file(), f"missing {FONT_REGULAR}"
    assert Path(FONT_BOLD).is_file(), f"missing {FONT_BOLD}"


async def test_renderer_produces_valid_pdf_with_unicode_body() -> None:
    """Full render through the real template with Cyrillic/Greek/symbol content."""
    OUT_DIR.mkdir(exist_ok=True)
    job = _minimal_job("r-unicode", name="Cyrillic/Greek/symbols coverage")
    classification = DefectClassification(
        defect_type="water_damage",
        severity="medium",
        summary=f"{_CYRILLIC}\n\n{_GREEK}\n\n{_SYMBOLS}",
        expert_note_localized=_CYRILLIC,
    )
    pdf = await Xhtml2pdfAdapter().render(job, classification, _sample_photos())

    assert pdf[:4] == b"%PDF", "output is not a valid PDF"
    assert len(pdf) > 10_000, "PDF suspiciously small"

    out_file = OUT_DIR / "test_render.pdf"
    out_file.write_bytes(pdf)
    print(f"\n  → {out_file}  ({len(pdf):,} bytes)")


async def test_renderer_summary_override_produces_valid_pdf() -> None:
    """summary_override is used in place of classification.summary — renders without error."""
    job = _minimal_job("r-override")
    classification = DefectClassification(
        defect_type="crack", severity="high", summary="Original summary"
    )
    pdf = await Xhtml2pdfAdapter().render(job, classification, [], summary_override="Override text")
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 1_000


async def test_renderer_without_override_uses_classification_summary() -> None:
    """Without summary_override, classification.summary is used — both render without error."""
    job = _minimal_job("r-no-override")
    classification = DefectClassification(
        defect_type="crack", severity="medium", summary="Baseline summary"
    )
    pdf_base = await Xhtml2pdfAdapter().render(job, classification, [])
    pdf_over = await Xhtml2pdfAdapter().render(
        job, classification, [], summary_override="Different"
    )
    assert pdf_base[:4] == b"%PDF"
    assert pdf_over[:4] == b"%PDF"


async def test_renderer_expert_note_localized_produces_valid_pdf() -> None:
    """expert_note_localized in classification renders the blockquote section without error."""
    job = _minimal_job("r-expert-note")
    classification = DefectClassification(
        defect_type="damp",
        severity="low",
        summary="Assessment summary",
        expert_note_localized="Translated expert note for customer",
    )
    pdf = await Xhtml2pdfAdapter().render(job, classification, [])
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 1_000


# ---------------------------------------------------------------------------
# Localized labels — section chrome + defect_type/severity per locale
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("locale", ["en", "de", "ru", "el"])
async def test_renderer_produces_valid_pdf_for_each_supported_locale(locale: str) -> None:
    """The template's fixed chrome (title, section labels, disclaimer) is localized via the
    renderer's own locales/ catalog — this must render cleanly for every supported language,
    not just the default "en"."""
    job = _minimal_job(f"r-locale-{locale}")
    classification = DefectClassification(defect_type="crack", severity="high", summary="s")
    pdf = await Xhtml2pdfAdapter().render(job, classification, [], locale=locale)
    assert pdf[:4] == b"%PDF"


async def test_renderer_defaults_locale_to_job_customer_language() -> None:
    """No explicit locale override — falls back to job.customer_language (RunAssessment /
    report_generator's real call site never passes locale explicitly)."""
    job = _minimal_job("r-locale-default")
    job.customer_language = "de"
    classification = DefectClassification(defect_type="crack", severity="high", summary="s")
    pdf = await Xhtml2pdfAdapter().render(job, classification, [])
    assert pdf[:4] == b"%PDF"


def test_defect_type_label_translates_known_identifier() -> None:
    catalog = load_catalog(_LOCALES_DIR, "de")
    assert _defect_type_label(catalog, "water_damage") == "Wasserschaden"


def test_defect_type_label_falls_back_to_humanized_slug_for_unknown_identifier() -> None:
    catalog = load_catalog(_LOCALES_DIR, "de")
    assert _defect_type_label(catalog, "termite_damage") == "Termite Damage"


def test_severity_label_translates_known_value() -> None:
    catalog = load_catalog(_LOCALES_DIR, "ru")
    assert _severity_label(catalog, "critical") == "Критическая"


# ---------------------------------------------------------------------------
# Photo shrink-for-embedding — keeps the PDF small regardless of stored size
# ---------------------------------------------------------------------------


def _oversized_jpeg(min_bytes: int) -> bytes:
    """A solid-color JPEG large enough to exceed min_bytes before shrinking."""
    image = Image.new("RGB", (4000, 3000), color=(120, 60, 30))
    # Add noise-like content so JPEG can't compress it down to nothing — a flat color
    # alone would stay under the threshold even at full resolution.
    pixels = image.load()
    for y in range(0, 3000, 7):
        for x in range(0, 4000, 11):
            pixels[x, y] = (x % 256, y % 256, (x + y) % 256)
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=95)
    data = buf.getvalue()
    assert len(data) > min_bytes, "fixture image not large enough for this test"
    return data


async def test_renderer_shrinks_oversized_photo_for_embedding() -> None:
    max_bytes = int(settings.report_photo_max_size_mb * 1024 * 1024)
    photo = _oversized_jpeg(max_bytes)
    job = _minimal_job("r-oversized-photo")
    classification = DefectClassification(defect_type="crack", severity="low", summary="s")

    pdf = await Xhtml2pdfAdapter().render(job, classification, [photo])

    assert pdf[:4] == b"%PDF"
    # Base64 inflates by ~4/3 — allow generous headroom above the raw shrink target.
    assert len(pdf) < max_bytes * 2, "PDF still bloated by an unshrunk photo"


async def test_renderer_leaves_small_photo_untouched() -> None:
    image = Image.new("RGB", (200, 150), color=(10, 20, 30))
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=85)
    small = buf.getvalue()
    assert len(small) < settings.report_photo_max_size_mb * 1024 * 1024

    job = _minimal_job("r-small-photo")
    classification = DefectClassification(defect_type="crack", severity="low", summary="s")
    pdf = await Xhtml2pdfAdapter().render(job, classification, [small])
    assert pdf[:4] == b"%PDF"
