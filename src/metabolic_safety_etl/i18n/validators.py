from __future__ import annotations

from dataclasses import dataclass
import re

from .placeholders import missing_placeholders


EXPLANATION_PREFIX_RE = re.compile(r"^\s*(?:以下是|这是|翻译[:：]|译文[:：]|translation\s*[:：]|the translation is)", re.I)
MARKDOWN_RE = re.compile(r"(^|\n)\s*(?:#{1,6}\s+|[-*+]\s+|\d+\.\s+)|\*\*[^*]+\*\*|__[^_]+__")
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
IDENTIFIER_RE = re.compile(r"\b(?:PMID|NDC|UNII|RxCUI|ATC|CHEMBL|ChEMBL)[:#\s-]*[A-Za-z0-9_.-]+\b|\brs\d+\b", re.I)
DOSE_UNIT_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:mg/kg/day|mg/kg/dose|mcg/kg/min|mcg/kg/day|mcg/kg|ug/kg|micrograms?/kg|mg/day|mg|mcg|ug|g|grams?|mL|ml|L|IU|units?|%)\b", re.I)
UNIT_CHINESE_DUPLICATE_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:mg/kg/day|mg/kg/dose|mcg/kg/min|mcg/kg/day|mcg/kg|ug/kg|mg/day|mg|mcg|ug|g|mL|ml|L|IU)\s*(?:毫克|微克|克|毫升|升|单位)", re.I)
UNIT_CHINESE_DUPLICATE_CLEAN_RE = re.compile(r"(\b\d+(?:\.\d+)?\s*(?:mg/kg/day|mg/kg/dose|mcg/kg/min|mcg/kg/day|mcg/kg|ug/kg|mg/day|mg|mcg|ug|g|mL|ml|L|IU))\s*(?:毫克|微克|克|毫升|升|单位)", re.I)


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    reasons: list[str]


def clean_translation_artifacts(translated_text: str) -> str:
    """Remove deterministic model artifacts that are safer to normalize than drop.

    The source unit token is preserved verbatim; only the duplicated Chinese unit
    appended by the model is removed (for example, "10 mg 毫克" -> "10 mg").
    """
    text = str(translated_text or "")
    previous = None
    while previous != text:
        previous = text
        text = UNIT_CHINESE_DUPLICATE_CLEAN_RE.sub(r"\1", text)
    return text


def _missing_tokens(source: str, translated: str, pattern: re.Pattern[str]) -> list[str]:
    tokens = sorted({match.group(0) for match in pattern.finditer(source)}, key=str.lower)
    missing = []
    for token in tokens:
        if token not in translated:
            missing.append(token)
    return missing


def validate_translation(source_text: str, translated_text: str, placeholders: dict[str, str] | None = None, protected_output: str | None = None) -> ValidationResult:
    reasons: list[str] = []
    source = str(source_text or "")
    translated = str(translated_text or "")
    if not translated.strip():
        reasons.append("empty_translation")
    if EXPLANATION_PREFIX_RE.search(translated):
        reasons.append("extra_explanation_prefix")
    if MARKDOWN_RE.search(translated):
        reasons.append("unexpected_markdown")
    if placeholders and protected_output is not None:
        missing = missing_placeholders(protected_output, placeholders)
        if missing:
            reasons.append("missing_placeholders:" + ",".join(missing[:8]))
    missing_ids = _missing_tokens(source, translated, IDENTIFIER_RE)
    if missing_ids:
        reasons.append("missing_identifiers:" + ",".join(missing_ids[:8]))
    missing_doses = _missing_tokens(source, translated, DOSE_UNIT_RE)
    if missing_doses:
        reasons.append("missing_dose_units:" + ",".join(missing_doses[:8]))
    unit_duplicates = sorted({match.group(0) for match in UNIT_CHINESE_DUPLICATE_RE.finditer(translated)})
    if unit_duplicates:
        reasons.append("duplicated_unit_translation:" + ",".join(unit_duplicates[:8]))
    source_numbers = sorted({match.group(0) for match in NUMBER_RE.finditer(source)})
    translated_numbers = set(match.group(0) for match in NUMBER_RE.finditer(translated))
    missing_numbers = [number for number in source_numbers if number not in translated_numbers]
    if len(missing_numbers) > 3 and len(missing_numbers) > len(source_numbers) // 2:
        reasons.append("many_missing_numbers:" + ",".join(missing_numbers[:8]))
    if len(translated) > max(500, len(source) * 5):
        reasons.append("translation_too_long")
    return ValidationResult(ok=not reasons, reasons=reasons)
