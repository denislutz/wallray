"""Generate test PDF reports locally using the xhtml2pdf adapter."""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.adapters.renderer.xhtml2pdf import Xhtml2pdfAdapter
from app.domain.job import DefectClassification, Job, JobStatus

SAMPLE_DIR = Path(__file__).parent.parent.parent / "docs" / "clusterindex" / "pics"
OUT_DIR = Path(__file__).parent.parent.parent / "docs" / "clusterindex"

RENDERER = Xhtml2pdfAdapter()

CLASSIFICATION = DefectClassification(
    defect_type="spalling",
    severity="high",
    notes=(
        "Significant spalling and paint loss visible along the lower portion of the wall, "
        "with exposed substrate and widespread deterioration. Multiple areas of paint peeling "
        "and material breakdown indicate advanced surface degradation."
    ),
)


def _make_job(n: int) -> Job:
    return Job(
        id=f"test-{n:04d}-photos",
        user_id="test-user",
        status=JobStatus.complete,
        photos=[],
        description="Whats this issue",
        created_at=datetime.now(UTC),
    )


def _load_photos(names: list[str]) -> list[bytes]:
    return [(SAMPLE_DIR / name).read_bytes() for name in names]


async def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    images = sorted(SAMPLE_DIR.iterdir())

    cases: list[tuple[str, list[str]]] = [
        ("report_1photo.pdf", [images[0].name]),
        ("report_2photos.pdf", [images[0].name, images[1].name]),
        ("report_4photos.pdf", [images[0].name, images[1].name, images[2].name, images[3].name]),
        ("report_6photos.pdf", [img.name for img in images[:6]]),
    ]

    for filename, photo_names in cases:
        out_path = OUT_DIR / filename
        photo_data = _load_photos(photo_names)
        job = _make_job(len(photo_names))
        pdf_bytes = await RENDERER.render(job, CLASSIFICATION, photo_data)
        out_path.write_bytes(pdf_bytes)
        print(f"  wrote {out_path.name}  ({len(pdf_bytes) // 1024} KB)")


if __name__ == "__main__":
    asyncio.run(main())
