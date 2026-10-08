from __future__ import annotations

import base64
import json
import re
from typing import Any, Literal

import anthropic

from app.domain.job import DefectClassification, IntakeResult, PhotoRole
from app.domain.ports.storage import StoragePort

_INTAKE_SYSTEM_PROMPT = """\
You are a fast pre-filter for a building-defect photo intake pipeline. You will be shown one or \
more photos submitted together as a single case.

Decide two things:
1. Is this a genuine building/property defect photo submission (walls, ceilings, facades, roofs, \
   foundations, cracks, damp, mould, etc.)? Reject junk: selfies, screenshots, unrelated objects, \
   memes, photos with no visible building surface at all.
2. For EACH photo, in the exact order given, assign a role:
   - "close_up": a tight shot of the defect itself (crack, stain, damage in detail).
   - "context": a wider shot showing where the defect sits in the building (facade, room, \
     surrounding structure).
   - "repeat_location": a photo of the same or a visually similar spot as another photo in this \
     same set (e.g. a second angle on the same crack).

Return ONLY valid JSON (no markdown fences, no extra text) with exactly these keys:
- accepted: true or false
- rejection_reason: one short sentence in English explaining why this was rejected, or null if accepted
- roles: an array of role strings, one per photo, in the same order the photos were given — each \
  one of "close_up", "context", "repeat_location"

Example: {{"accepted": true, "rejection_reason": null, "roles": ["close_up", "context"]}}"""

_ASSESS_SYSTEM_PROMPT = """\
You are an experienced building surveyor analysing photos of a possible building defect. You will \
be shown all photos submitted for this case together — treat close-up photos as detail evidence \
and context/wide photos as the structural evidence for WHY the defect sits where it does.

Do not stop at a superficial label like "this is a crack" or "this is peeling paint" — that alone \
is worthless, it's visible in the photo itself. Your real job is to use the context photos to \
reason through WHY this defect is occurring at this exact location:

- Where exactly does this sit in the building (foundation, window corner, balcony junction, roof \
  edge, interior, weather-facing side)?
- What water paths, load paths, or building-component junctions visible in the context photos \
  explain the damage pattern in the close-up?
- Are there visible clues to the cause in the context photos (missing/damaged sealant, junction \
  gap, drainage, orientation to weather, crack path relative to openings or component edges)?
- If a wet room (bathroom, kitchen, WC) could plausibly sit behind this facade location, consider \
  whether the cause is more likely interior condensation/humidity pushing outward through the \
  window/wall than external causes (rain, windowsill leak). State both possibilities if the photos \
  don't clearly settle it.

PRIOR ASSESSMENT (if provided below): your own previous round's `summary` for this case. Treat it \
as the depth/structure baseline — preserve and extend it, never shrink it to a shorter paraphrase. \
Re-examine the photos yourself rather than just repeating it. The never-shrink rule applies to the \
depth of reasoning, not to open questions: when a customer reply or expert note resolves an item \
from the prior round's Further checks, fold the answer into the finding/cause narrative and drop \
it from the open checks — don't keep answered items listed as open.

CONTEXT SIGNALS (may be empty): structured facts for this case — intake-form fields and any \
customer replies, labeled by round. Supporting evidence to weigh alongside the photos, never more \
authoritative than what you can see yourself.

EXPERT NOTES (if provided below): a certified expert has physically reviewed this case; their \
findings take priority over your own prior reasoning on conflict — defer to them, but still use \
the photos yourself to explain how their finding relates to what's visible.

ATTRIBUTION: whenever you incorporate a customer reply or expert note into the reasoning, say so \
explicitly in the narrative (e.g. "Per your reply, ...", "Per the reviewing expert's on-site \
finding, ...") rather than blending it in silently — the reader should be able to tell what came \
from where.

CRITICAL LANGUAGE RULE: You MUST write `summary` in {customer_language} (ISO 639-1 code) — a hard \
requirement regardless of what language the context signals, prior assessment, or expert notes are \
in. See `summary_expert` / `expert_note_localized` / `verification_items` below for their own \
language conditions.

FORMATTING: `summary` and `summary_expert` are rendered through a markdown viewer, not shown as raw \
text — use markdown to make them scannable the way a well-formatted report reads: a bold label per \
section (e.g. `**Finding:**`), short paragraphs, and a bullet list (`- item`) wherever you're \
listing more than one thing. This is about structure, not decoration — no headings, no tables, no \
code blocks, and don't force a bullet list where a single sentence reads better. The JSON string \
value itself is unaffected — write the markdown source with literal `\n` line breaks inside the \
string, exactly like any other multi-line JSON string value.

Return ONLY valid JSON (no markdown fences, no extra text) with exactly these keys:
- defect_type: short identifier, e.g. "crack", "water_damage", "mould", "spalling", "none"
- severity: one of "low", "medium", "high", "critical"
- summary: the full assessment in markdown, in {customer_language}, covering, in order: (1) \
  **Finding** — what is visible, (2) **Probable cause** — your reasoned derivation, not just the \
  symptom, (3) **Severity reasoning**, (4) **Further checks** — what else should be checked to \
  confirm the cause, as a bullet list if there's more than one. Same depth every round.
- summary_expert: the same assessment, same depth, in {expert_language}, or null if it matches \
  {customer_language}
- expert_note_localized: the expert's note translated into {customer_language} verbatim (not \
  paraphrased), or null if no expert notes were provided
- confidence: a float from 0.0 to 1.0 reflecting how confident you are in this assessment given \
  the photos and context available
- verification_items: an array of objects, each {{"text": "...", "kind": "..."}}, for anything \
  from point (4) above worth flagging — kind is one of:
  - "customer_question": the customer could answer this directly in text (e.g. building age, \
    "is there a drip irrigation line against this wall?") — write `text` in {customer_language}
  - "photo_request": this needs a new photo, not a text answer (e.g. "photograph the interior \
    wall directly behind this location") — write `text` in English
  - "expert_only_check": this needs a tool or person on site (e.g. moisture meter reading, \
    opening a section) — never phrase these as something the customer can just answer; write \
    `text` in English
  When expert notes are provided, include only items still open after the expert's on-site \
  findings — often none. May be an empty array if there's nothing further worth flagging."""

_ImageMediaType = Literal["image/jpeg", "image/png", "image/gif", "image/webp"]

_ROLE_VALUES = frozenset(r.value for r in PhotoRole)


def _media_type(data: bytes) -> _ImageMediaType:
    if data[:4] == b"\x89PNG":
        return "image/png"
    return "image/jpeg"


def _extract_text(content: list[anthropic.types.ContentBlock]) -> str:
    # Models with extended thinking can return a ThinkingBlock before the
    # TextBlock — content[0] isn't reliably the text, so scan for it.
    for block in content:
        if block.type == "text":
            return block.text
    raise ValueError("No text block in Anthropic response")


def _parse_json(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    payload: dict[str, Any] = json.loads(cleaned)
    return payload


class AnthropicAdapter:
    def __init__(
        self,
        api_key: str,
        storage: StoragePort,
        classification_model: str = "claude-haiku-4-5-20251001",
        assessment_model: str = "claude-fable-5",
    ) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._storage = storage
        self._classification_model = classification_model
        self._assessment_model = assessment_model

    async def _photo_content(
        self, photo_keys: list[str]
    ) -> list[anthropic.types.ContentBlockParam]:
        content: list[anthropic.types.ContentBlockParam] = []
        for key in photo_keys:
            data = await self._storage.download(key)
            b64 = base64.standard_b64encode(data).decode()
            media_type = _media_type(data)
            content.append(
                anthropic.types.ImageBlockParam(
                    type="image",
                    source=anthropic.types.Base64ImageSourceParam(
                        type="base64",
                        media_type=media_type,
                        data=b64,
                    ),
                )
            )
        return content

    async def validate_intake(self, photo_keys: list[str]) -> IntakeResult:
        content = await self._photo_content(photo_keys)
        content.append(
            anthropic.types.TextBlockParam(
                type="text",
                text="Assess whether these photos are a valid building-defect submission and "
                "tag each photo's role, in order.",
            )
        )
        response = await self._client.messages.create(
            model=self._classification_model,
            max_tokens=512,
            system=_INTAKE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
        payload = _parse_json(_extract_text(response.content))
        roles_raw = payload.get("roles") or []
        photo_roles: dict[str, PhotoRole] = {}
        for key, role in zip(photo_keys, roles_raw, strict=False):
            if role in _ROLE_VALUES:
                photo_roles[key] = PhotoRole(role)
        return IntakeResult(
            accepted=bool(payload.get("accepted")),
            rejection_reason=str(payload["rejection_reason"])
            if payload.get("rejection_reason")
            else None,
            photo_roles=photo_roles,
        )

    async def translate(self, text: str, target_language: str) -> str:
        response = await self._client.messages.create(
            model=self._classification_model,
            max_tokens=512,
            system="You are a translator. Return only the translated text, nothing else.",
            messages=[
                {
                    "role": "user",
                    "content": f"Translate to {target_language}:\n\n{text}",
                }
            ],
        )
        return _extract_text(response.content).strip()

    async def assess(
        self,
        photo_keys: list[str],
        context_signals: dict[str, Any],
        prior_summary: str | None = None,
        expert_notes: str | None = None,
        customer_language: str = "en",
        expert_language: str | None = None,
    ) -> DefectClassification:
        content = await self._photo_content(photo_keys)
        text = f"Context signals collected for this case:\n{json.dumps(context_signals)}\n\n"
        if prior_summary:
            text += f"Prior assessment:\n{prior_summary}\n\n"
        if expert_notes:
            text += f"Expert notes:\n{expert_notes}\n\n"
        text += "Analyse these photos and return the JSON assessment."
        content.append(anthropic.types.TextBlockParam(type="text", text=text))
        response = await self._client.messages.create(
            model=self._assessment_model,
            max_tokens=8192,
            system=_ASSESS_SYSTEM_PROMPT.format(
                customer_language=customer_language,
                expert_language=expert_language or customer_language,
            ),
            messages=[{"role": "user", "content": content}],
        )
        payload = _parse_json(_extract_text(response.content))
        return DefectClassification(
            defect_type=str(payload["defect_type"]),
            severity=str(payload["severity"]),
            summary=str(payload["summary"]) if payload.get("summary") else None,
            summary_expert=str(payload["summary_expert"])
            if payload.get("summary_expert")
            else None,
            expert_note_localized=str(payload["expert_note_localized"])
            if payload.get("expert_note_localized")
            else None,
            confidence=float(payload["confidence"])
            if payload.get("confidence") is not None
            else None,
            verification_items=list(payload.get("verification_items") or []),
        )
