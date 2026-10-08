from __future__ import annotations

import base64
import json
from typing import Any

import openai

from app.domain.job import DefectClassification
from app.domain.ports.storage import StoragePort

_CLASSIFY_SYSTEM_PROMPT = """\
You are an expert building inspector analysing wall and surface photos for defects.
Return ONLY valid JSON (no markdown fences, no extra text) with exactly these keys:
- defect_type: short identifier, e.g. "crack", "water_damage", "mould", "spalling", "none"
- severity: one of "low", "medium", "high", "critical"
- notes: one or two sentences summarising findings in {language} (ISO 639-1 language code), or null\
"""


def _data_url(data: bytes) -> str:
    media_type = "image/png" if data[:4] == b"\x89PNG" else "image/jpeg"
    b64 = base64.standard_b64encode(data).decode()
    return f"data:{media_type};base64,{b64}"


class OpenAIAdapter:
    def __init__(
        self,
        api_key: str,
        storage: StoragePort,
        model: str = "gpt-4o-mini",
    ) -> None:
        # Defer SDK validation to call time — avoids crashing the server at
        # startup when the key isn't configured yet.
        self._api_key = api_key
        self._storage = storage
        self._model = model
        self._client: openai.AsyncOpenAI | None = None

    def _get_client(self) -> openai.AsyncOpenAI:
        if self._client is None:
            # api_key="" would be rejected by the SDK; pass None so it reads
            # the OPENAI_API_KEY env var as a fallback before raising.
            self._client = openai.AsyncOpenAI(api_key=self._api_key or None)
        return self._client

    async def classify(self, photo_keys: list[str], language: str = "en") -> DefectClassification:
        client = self._get_client()
        user_parts: list[Any] = []
        for key in photo_keys:
            data = await self._storage.download(key)
            user_parts.append({"type": "image_url", "image_url": {"url": _data_url(data)}})
        user_parts.append(
            {
                "type": "text",
                "text": "Analyse these wall/surface images and return the JSON classification.",
            }
        )

        messages: list[Any] = [
            {"role": "system", "content": _CLASSIFY_SYSTEM_PROMPT.format(language=language)},
            {"role": "user", "content": user_parts},
        ]
        response = await client.chat.completions.create(
            model=self._model,
            max_tokens=512,
            messages=messages,
        )
        raw = (response.choices[0].message.content or "").strip()
        payload: dict[str, str | None] = json.loads(raw)
        return DefectClassification(
            defect_type=str(payload["defect_type"]),
            severity=str(payload["severity"]),
            summary=str(payload["notes"]) if payload.get("notes") else None,
        )
