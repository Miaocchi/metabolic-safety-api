from __future__ import annotations

import re


SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.;!?。！？；])\s+")


def normalize_segment_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def segment_text(text: str, max_chars: int = 1800) -> list[str]:
    """Split long fields into stable translation segments.

    The function is deterministic and shared by candidate extraction and overlay
    export, so translation memory can be looked up per segment.
    """
    clean = normalize_segment_text(text)
    if not clean:
        return []
    if max_chars <= 0 or len(clean) <= max_chars:
        return [clean]
    sentences = [part.strip() for part in SENTENCE_BOUNDARY_RE.split(clean) if part.strip()]
    if not sentences:
        sentences = [clean]
    segments: list[str] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > max_chars:
            if current:
                segments.append(current.strip())
                current = ""
            for idx in range(0, len(sentence), max_chars):
                chunk = sentence[idx:idx + max_chars].strip()
                if chunk:
                    segments.append(chunk)
            continue
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                segments.append(current.strip())
            current = sentence
    if current:
        segments.append(current.strip())
    return segments
