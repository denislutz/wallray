# BE Image Handling Plan

Two features: (1) raise upload cap to 20 MB with auto-downscale above 12 MB, and (2) generate a real thumbnail on upload for lists and fast-load previews.

---

## AI Classification Impact of 50% Downscale

**Short answer: negligible for building defect classification.**

Claude Vision internally caps images at ~1 568 px on the long edge before sending to the model. A typical 15 MB phone photo is ~5 000 × 3 750 px; at 50 % linear scale (25 % pixel count) it becomes ~2 500 × 1 875 px — still larger than Claude's internal cap. The model never sees the extra pixels anyway.

Building defects that matter for classification (cracks, mold, water damage, delamination, corrosion) are large-area features that read clearly at 2 MP. Sub-millimetre hairline cracks are the edge case, but at smartphone sensor size they rarely survive JPEG compression at original quality either.

**Rule of thumb:** if the image is ≥ 12 MP after resize, classification fidelity is unaffected. Images below 12 MP before resize are never touched.

---

## Feature 1 — Raise cap to 20 MB + auto-downscale above 12 MB

### Config (`be/app/core/config.py`)

| Setting | Old | New |
|---|---|---|
| `photo_max_size_mb` | `10` | `20` |
| `photo_resize_threshold_mb` (new) | — | `12` |

### Upload flow (`be/app/application/upload_job.py`)

After `_check_magic_bytes`, before `storage.upload`:

```
if len(data) > settings.photo_resize_threshold_mb * 1024 * 1024:
    data, content_type = _downscale(data, target_factor=0.5)
```

`_downscale` (private):

1. `Image.open(io.BytesIO(data))`
2. `img.resize((w // 2, h // 2), Image.LANCZOS)`
3. Save to `io.BytesIO` as JPEG quality 85
4. Return `(bytes, "image/jpeg")`

HEIC/HEIF files are always converted to JPEG by this path (Pillow cannot write HEIC). This is a benefit, not a loss — HEIC stays opaque in S3 otherwise.

### No schema or migration changes needed — the stored key and content_type update in place

---

## Feature 2 — True thumbnail per photo (max 400 px wide)

### Problem with current state

`job.thumbnail_key = photos[0].key` — it points to the full-size (or downscaled) photo. The FE `Thumbnail` component loads a multi-MB image for a 64 px avatar.

### Domain model changes

**`be/app/domain/job.py`** — `Photo` dataclass:

```python
@dataclass
class Photo:
    key: str
    content_type: str
    thumb_key: str | None = None   # new
```

**`be/app/adapters/persistence/orm_models.py`** — `PhotoRow`:

```python
thumb_key: Mapped[str | None] = mapped_column(String, nullable=True)
```

→ Alembic migration required (`alembic revision --autogenerate -m "add photo thumb_key"`)

**`be/app/adapters/persistence/pg_job_repo.py`** — map `thumb_key` in `_row_to_photo` and `_photo_to_values`.

### Upload flow addition (`upload_job.py`)

After storing the main image, generate the thumbnail:

```
thumb_bytes = _make_thumbnail(data, max_px=400)
thumb_key = f"jobs/{job_id}/thumbs/{uuid4()}"
await self._storage.upload(thumb_key, thumb_bytes, "image/jpeg")
photos.append(Photo(key=key, content_type=content_type, thumb_key=thumb_key))
```

`_make_thumbnail` (private):

1. `img = Image.open(io.BytesIO(data))`
2. `w, h = img.size`
3. If `w > 400`: `new_h = round(400 * h / w); img = img.resize((400, new_h), Image.LANCZOS)`
4. Save to JPEG quality 80, return bytes

If the image is already ≤ 400 px wide, copy as-is (no upscale).

### Job construction

```python
job = Job(
    ...
    thumbnail_key=photos[0].thumb_key or photos[0].key,  # fallback for safety
    ...
)
```

The `thumbnail_key` column and all existing FE consumers (`ReportsPage`, `ExpertQueuePage`, `ReportPage`) get the real thumbnail automatically — no FE changes needed for those views.

### Admin expert review — photo grid

Currently `photo_urls` returns full-size signed URLs; the grid `<img>` loads full photos. Add a parallel `photo_thumb_urls` list so the grid shows thumbs and clicking opens the full URL.

**`be/app/api/schemas.py`**:

```python
photo_thumb_urls: list[str] | None = None
```

**`be/app/api/routes/admin.py`** — `get_job_for_review`:

```python
photo_thumb_urls = [
    await storage.signed_url(p.thumb_key)
    for p in job.photos
    if p.thumb_key
]
```

**`fe/services/business/JobS.ts`** — `Report` interface:

```ts
photo_thumb_urls: string[] | null;
```

**`fe/ui/business/ExpertReviewPage.tsx`** — photo grid:

```tsx
<a key={url} href={url} target="_blank" rel="noreferrer">
  <img src={thumbUrl ?? url} alt="" ... />
</a>
```

(zip `photo_urls` and `photo_thumb_urls` by index)

---

## S3 Key Layout After Implementation

```
jobs/{job_id}/
  {uuid}          ← original upload (possibly downscaled to ≤ 12 MB)
  {uuid}          ← second photo
  thumbs/
    {uuid}        ← thumbnail for photo 1 (≤ 400 px wide, JPEG 80 %)
    {uuid}        ← thumbnail for photo 2
```

---

## Implementation Order

1. `config.py` — add `photo_resize_threshold_mb = 12`, bump `photo_max_size_mb` to 20
2. `job.py` — add `thumb_key` to `Photo`
3. `orm_models.py` — add `thumb_key` column → run `alembic revision --autogenerate`
4. `pg_job_repo.py` — map `thumb_key`
5. `upload_job.py` — add `_downscale` + `_make_thumbnail`, update `execute`
6. `schemas.py` — add `photo_thumb_urls`
7. `admin.py` — populate `photo_thumb_urls` in `get_job_for_review`
8. `fe/services/business/JobS.ts` — add `photo_thumb_urls`
9. `fe/ui/business/ExpertReviewPage.tsx` — use thumb for grid `<img>`, full URL for `<a href>`
10. Tests — update `test_upload.py` to assert `thumb_key` is set; update admin tests for `photo_thumb_urls`
11. `qa:local` → push
