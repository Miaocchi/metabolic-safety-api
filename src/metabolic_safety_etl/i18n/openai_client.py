from __future__ import annotations

from dataclasses import dataclass
import json
import urllib.error
import urllib.request


PROMPT_VERSION = "hunyuan_mt_zh_cn_v1"


def build_translation_prompt(text: str, target_language: str = "Simplified Chinese", strict: bool = False) -> str:
    extra = ""
    if strict:
        extra = "\nOnly output the translated text. Do not include labels, explanations, markdown, quotes, or alternative translations."
    return (
        f"Translate the following English medical/pharmacology text into {target_language}.\n"
        "Output plain text only.\n"
        "Do not add explanations.\n"
        "Do not add markdown, bold text, bullet points, headings, or line breaks that are not present in the source.\n"
        "Do not omit any information.\n"
        "Preserve placeholders such as <PH001>, <PH002>, gene symbols, variant IDs, units, numbers, URLs, PMIDs, NDCs, UNII and RxCUI identifiers.\n"
        "If the input is already Chinese, return it unchanged."
        f"{extra}\n\n"
        f"{text}"
    )


@dataclass(frozen=True)
class OpenAICompatibleClient:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: int = 120
    temperature: float = 0.2
    top_p: float = 0.6
    top_k: int | None = 20
    repetition_penalty: float | None = 1.05
    minimal_payload: bool = False

    def endpoint(self) -> str:
        return self.base_url.rstrip("/") + "/chat/completions"

    def translate(self, text: str, *, target_language: str = "Simplified Chinese", strict: bool = False) -> str:
        prompt = build_translation_prompt(text, target_language=target_language, strict=strict)
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if not self.minimal_payload:
            payload.update({"temperature": self.temperature, "top_p": self.top_p})
            if self.top_k is not None:
                payload["top_k"] = self.top_k
            if self.repetition_penalty is not None:
                payload["repetition_penalty"] = self.repetition_penalty
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint(),
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise RuntimeError(f"OpenAI-compatible API HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"OpenAI-compatible API request failed: {exc}") from exc
        return parse_chat_completion(response_payload)


def parse_chat_completion(payload: dict[str, object]) -> str:
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict) and message.get("content") is not None:
                return str(message.get("content") or "").strip()
            if first.get("text") is not None:
                return str(first.get("text") or "").strip()
    for key in ("output_text", "text", "content"):
        if payload.get(key) is not None:
            return str(payload.get(key) or "").strip()
    raise RuntimeError(f"Unable to parse chat completion response keys={sorted(payload.keys())}")
