from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


PLACEHOLDER_RE = re.compile(r"<PH\d{3}>")

TOKEN_PATTERNS = [
    re.compile(r"https?://[^\s)\]}>,;]+", re.I),
    re.compile(r"\b(?:PMID|NDC|UNII|RxCUI|ATC|CHEMBL|ChEMBL)[:#\s-]*[A-Za-z0-9_.-]+\b", re.I),
    re.compile(r"\brs\d+\b", re.I),
    re.compile(r"\b\d+(?:\.\d+)?\s*(?:mg/kg/day|mg/kg/dose|mcg/kg/min|mcg/kg/day|mcg/kg|ug/kg|micrograms?/kg|mg/day|mg|mcg|ug|g|grams?|mL|ml|L|IU|units?|%)\b", re.I),
    re.compile(r"\b(?:CYP\d+[A-Z]?\d*|UGT\d+[A-Z]?\d*|SLCO\d+[A-Z]?\d*|SLC\d+[A-Z]?\d*|ABCB1|ABCG2|VKORC1|HLA-[A-Z0-9:*.-]+|G6PD|TPMT|DPYD|CYP2D6|CYP2C9|CYP2C19|CYP3A4|CYP3A5)\b"),
]


@dataclass(frozen=True)
class ProtectedText:
    text: str
    placeholders: dict[str, str]


def _add_span(spans: list[tuple[int, int]], start: int, end: int) -> None:
    if start >= end:
        return
    for existing_start, existing_end in spans:
        if start < existing_end and end > existing_start:
            return
    spans.append((start, end))


def _term_pattern(term: str) -> re.Pattern[str] | None:
    term = str(term or "").strip()
    if len(term) < 4:
        return None
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", re.I)


def protect_text(text: str, glossary_terms: Iterable[str] | None = None) -> ProtectedText:
    """Replace fragile biomedical tokens with placeholders before MT.

    Placeholders are restored verbatim after translation. This keeps IDs, genes,
    URLs and dose units from being translated or reformatted by the model.
    """
    source = str(text or "")
    spans: list[tuple[int, int]] = []
    for pattern in TOKEN_PATTERNS:
        for match in pattern.finditer(source):
            _add_span(spans, match.start(), match.end())
    terms = sorted({str(term).strip() for term in glossary_terms or [] if str(term).strip()}, key=len, reverse=True)
    for term in terms[:2000]:
        pattern = _term_pattern(term)
        if not pattern:
            continue
        for match in pattern.finditer(source):
            _add_span(spans, match.start(), match.end())
    if not spans:
        return ProtectedText(source, {})
    placeholders: dict[str, str] = {}
    parts: list[str] = []
    cursor = 0
    for idx, (start, end) in enumerate(sorted(spans)):
        placeholder = f"<PH{idx + 1:03d}>"
        parts.append(source[cursor:start])
        parts.append(placeholder)
        placeholders[placeholder] = source[start:end]
        cursor = end
    parts.append(source[cursor:])
    return ProtectedText("".join(parts), placeholders)


def restore_text(text: str, placeholders: dict[str, str]) -> str:
    restored = str(text or "")
    for placeholder, original in placeholders.items():
        restored = restored.replace(placeholder, original)
    return restored


def missing_placeholders(text: str, placeholders: dict[str, str]) -> list[str]:
    translated = str(text or "")
    return [placeholder for placeholder in placeholders if placeholder not in translated]
