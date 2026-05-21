from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any


RISK_LEVEL_ZH = {
    "Contraindicated": "禁忌合用",
    "Major": "高风险",
    "High": "高风险",
    "Moderate": "中等风险",
    "Minor": "低风险",
    "Low": "低风险",
    "NoKnownClinicalSignificance": "暂无已知临床意义",
    "Unknown": "未知风险",
}

CONFIDENCE_ZH = {
    "High": "高可信度",
    "Medium": "中等可信度",
    "Low": "低可信度",
    "Unknown": "未知可信度",
}

SOURCE_TIER_ZH = {
    "Regulatory": "监管来源",
    "Guideline": "指南来源",
    "Label": "药品标签来源",
    "CuratedDB": "策展数据库",
    "Literature": "文献来源",
    "Signal": "信号来源",
    "Community": "社区来源",
    "ManualReview": "人工复核来源",
    "LicensedCommercial": "授权商业来源",
    "Fixture": "测试夹具来源",
    "Unknown": "未知来源",
}

INTERACTION_TYPE_ZH = {
    "drug_interaction": "药物相互作用",
    "food_interaction": "食物/生物活性物相互作用",
    "adverse_event_signal": "不良事件信号",
    "interaction": "相互作用",
}

ACTION_ZH = {
    "highest_alert": "最高级别提醒",
    "avoid_or_modify_therapy": "避免合用或调整治疗方案",
    "monitor_closely": "密切监测",
    "caution_or_spacing": "谨慎使用或错开给药",
    "silent_unless_requested": "仅在需要时显示",
    "show_uncertainty": "显示不确定性",
    "review_required": "需要复核",
    "candidate_signal": "候选信号",
    "evidence_only": "仅作证据展示",
    "not_causal": "不代表因果关系",
    "text_mined": "文本挖掘候选",
}

ROUTE_ZH = {
    "oral": "口服",
    "po": "口服",
    "intravenous": "静脉给药",
    "iv": "静脉给药",
    "subcutaneous": "皮下注射",
    "sc": "皮下注射",
    "intramuscular": "肌肉注射",
    "im": "肌肉注射",
    "sublingual": "舌下给药",
    "intranasal": "鼻腔给药",
    "nasal": "鼻用",
    "topical": "外用",
    "transdermal": "经皮给药",
    "inhalation": "吸入",
    "ophthalmic": "眼用",
    "otic": "耳用",
    "rectal": "直肠给药",
    "vaginal": "阴道给药",
}

REVIEW_STATUS_ZH = {
    "reviewed": "已复核",
    "unreviewed": "未复核",
    "review_required": "需要复核",
    "machine_unreviewed": "机器翻译，未人工复核",
    "machine_reviewed": "机器翻译，已复核",
    "curated": "人工校对",
    "failed_validation": "校验失败",
    "pending": "待处理",
}

SECTION_ZH = {
    "clinical_pharmacology": "临床药理",
    "pharmacodynamics": "药效学",
    "pharmacokinetics": "药代动力学",
    "indications_and_usage": "适应症和用法",
    "purpose": "用途",
    "mechanism_of_action": "作用机制",
    "drug_interactions": "药物相互作用",
    "warnings": "警告",
    "boxed_warning": "黑框警告",
    "overdosage": "过量用药",
    "dosage_and_administration": "剂量与给药方法",
    "label_section": "标签文段",
    "drug_effect": "药效证据",
    "interaction": "相互作用",
}

THRESHOLD_LABEL_ZH = {
    "maximum daily dose": "每日最大剂量",
    "max daily dose": "每日最大剂量",
    "maximum recommended daily dose": "每日最大推荐剂量",
    "maximum total daily dose": "每日总最大剂量",
    "maximum single dose": "单次最大剂量",
    "single dose": "单次剂量",
    "window dose": "时间窗口剂量",
    "daily ceiling": "每日剂量上限",
    "screening threshold": "筛查阈值",
}

ACTION_TYPE_ZH = {
    "inhibitor": "抑制剂",
    "inhibition": "抑制作用",
    "agonist": "激动剂",
    "antagonist": "拮抗剂",
    "substrate": "底物",
    "inducer": "诱导剂",
    "induction": "诱导作用",
    "blocker": "阻滞剂",
    "binder": "结合剂",
    "activator": "激活剂",
}

AGE_GROUP_ZH = {
    "adult": "成人",
    "adults": "成人",
    "pediatric": "儿童/青少年",
    "children": "儿童",
    "child": "儿童",
    "adolescent": "青少年",
    "geriatric": "老年人",
    "elderly": "老年人",
}


CONTROLLED_BY_FIELD = {
    "risk_level": RISK_LEVEL_ZH,
    "level": RISK_LEVEL_ZH,
    "confidence": CONFIDENCE_ZH,
    "source_tier": SOURCE_TIER_ZH,
    "interaction_type": INTERACTION_TYPE_ZH,
    "action": ACTION_ZH,
    "review_status": REVIEW_STATUS_ZH,
    "route": ROUTE_ZH,
    "section": SECTION_ZH,
    "threshold_label": THRESHOLD_LABEL_ZH,
    "candidate_kind": THRESHOLD_LABEL_ZH,
    "action_type": ACTION_TYPE_ZH,
    "age_group": AGE_GROUP_ZH,
    "signal_policy": ACTION_ZH,
    "policy": ACTION_ZH,
    "use_policy": ACTION_ZH,
}

DDINTER_NOTE_RE = re.compile(
    r"DDInter\s+(?P<version>[0-9.]+)\s+severity=(?P<severity>[^;]+);\s+raw_levels=(?P<raw>[^;]+);\s+labels=(?P<labels>.+)",
    re.I,
)


def normalize_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[_\-]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def translate_controlled(field_name: str, value: Any) -> str | None:
    """Translate controlled vocabulary values without calling an LLM."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if field_name == "threshold_label" and re.search(r"[\u4e00-\u9fff]", raw):
        return raw
    table = CONTROLLED_BY_FIELD.get(field_name)
    if not table:
        return None
    if raw in table:
        return table[raw]
    normalized = normalize_key(raw)
    for key, zh in table.items():
        if normalize_key(key) == normalized:
            return zh
    if field_name == "threshold_label":
        dynamic = translate_dynamic_threshold_label(raw)
        if dynamic:
            return dynamic
    return None


def translate_dynamic_threshold_label(value: str) -> str | None:
    text = str(value or "").strip()
    match = re.fullmatch(r"24h total reaches/exceeds (\d+(?:\.\d+)?)x extracted dose candidate (.+)", text, flags=re.I)
    if match:
        multiple = match.group(1).strip()
        dose = match.group(2).strip()
        return f"24 小时累计达到/超过提取剂量候选值 {dose} 的 {multiple} 倍"
    match = re.fullmatch(r"24h total reaches/exceeds (\d+(?:\.\d+)?)x extracted label ceiling (.+)", text, flags=re.I)
    if match:
        multiple = match.group(1).strip()
        dose = match.group(2).strip()
        return f"24 小时累计达到/超过提取标签上限 {dose} 的 {multiple} 倍"
    match = re.fullmatch(r"24h total reaches/exceeds extracted dose candidate (.+)", text, flags=re.I)
    if match:
        dose = match.group(1).strip()
        return f"24 小时累计达到/超过提取剂量候选值 {dose}"
    match = re.fullmatch(r"24h total reaches/exceeds extracted label ceiling (.+)", text, flags=re.I)
    if match:
        dose = match.group(1).strip()
        return f"24 小时累计达到/超过提取标签上限 {dose}"
    match = re.fullmatch(r"24h total reaches/exceeds common max daily dose (.+)", text, flags=re.I)
    if match:
        dose = match.group(1).strip()
        return f"24 小时累计达到/超过常见最高日剂量 {dose}"
    match = re.fullmatch(r"single dose reaches/exceeds (\d+(?:\.\d+)?)x extracted dose candidate (.+)", text, flags=re.I)
    if match:
        multiple = match.group(1).strip()
        dose = match.group(2).strip()
        return f"单次剂量达到/超过提取剂量候选值 {dose} 的 {multiple} 倍"
    match = re.fullmatch(r"single dose reaches/exceeds (\d+(?:\.\d+)?)x extracted label ceiling (.+)", text, flags=re.I)
    if match:
        multiple = match.group(1).strip()
        dose = match.group(2).strip()
        return f"单次剂量达到/超过提取标签上限 {dose} 的 {multiple} 倍"
    match = re.fullmatch(r"single dose reaches/exceeds extracted dose candidate (.+)", text, flags=re.I)
    if match:
        dose = match.group(1).strip()
        return f"单次剂量达到/超过提取剂量候选值 {dose}"
    match = re.fullmatch(r"single dose reaches/exceeds extracted label ceiling (.+)", text, flags=re.I)
    if match:
        dose = match.group(1).strip()
        return f"单次剂量达到/超过提取标签上限 {dose}"
    match = re.fullmatch(r"24h total reaches/exceeds (.+)", text, flags=re.I)
    if match:
        dose = match.group(1).strip()
        return f"24 小时累计达到/超过 {dose}"
    match = re.fullmatch(r"single dose reaches/exceeds (.+)", text, flags=re.I)
    if match:
        dose = match.group(1).strip()
        return f"单次剂量达到/超过 {dose}"
    match = re.fullmatch(r"(?:about|approximately|approx\.?)\s+(.+?)\s+standard drinks?", text, flags=re.I)
    if match:
        amount = match.group(1).strip()
        return f"约 {amount} 个标准杯"
    return None


def translate_structured_text(field_name: str, value: Any) -> str | None:
    """Translate deterministic source notes without sending sensitive labels to an LLM."""
    raw = str(value or "").strip()
    if not raw:
        return None
    if field_name == "note":
        match = DDINTER_NOTE_RE.fullmatch(raw)
        if match:
            version = match.group("version")
            severity = match.group("severity").strip()
            raw_levels = match.group("raw").strip()
            labels = match.group("labels").strip()
            severity_zh = translate_controlled("risk_level", severity) or severity
            return f"DDInter {version} 严重程度={severity_zh}；原始等级={raw_levels}；标签={labels}"
    return None


def controlled_dictionary_payload() -> dict[str, dict[str, str]]:
    return {
        "risk_level": RISK_LEVEL_ZH,
        "confidence": CONFIDENCE_ZH,
        "source_tier": SOURCE_TIER_ZH,
        "interaction_type": INTERACTION_TYPE_ZH,
        "action": ACTION_ZH,
        "route": ROUTE_ZH,
        "review_status": REVIEW_STATUS_ZH,
        "section": SECTION_ZH,
        "threshold_label": THRESHOLD_LABEL_ZH,
        "action_type": ACTION_TYPE_ZH,
        "age_group": AGE_GROUP_ZH,
    }


def split_aliases(value: str) -> list[str]:
    aliases: list[str] = []
    for part in str(value or "").replace(";", "|").replace(",", "|").split("|"):
        alias = part.strip().strip('"').strip("'")
        if alias and alias not in aliases:
            aliases.append(alias)
    return aliases


def load_zh_aliases(path: Path | None) -> dict[str, dict[str, Any]]:
    """Load name_en/name_zh/aliases CSV into a normalized lookup."""
    if not path or not path.exists():
        return {}
    lookup: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            name_en = str(row.get("name_en") or "").strip()
            name_zh = str(row.get("name_zh") or "").strip()
            if not name_en or not name_zh:
                continue
            aliases = split_aliases(str(row.get("aliases") or ""))
            lookup[normalize_key(name_en)] = {
                "name_en": name_en,
                "name_zh": name_zh,
                "aliases": aliases,
                "status": "curated",
                "source": "drug_zh_aliases.csv",
            }
    return lookup


def entity_translation_for(item: dict[str, Any], zh_aliases: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    name_en = str(item.get("name_en") or item.get("name") or "").strip()
    existing_zh = str(item.get("name_zh") or "").strip()
    alias_hit = zh_aliases.get(normalize_key(name_en)) if name_en else None
    name_zh = existing_zh or (alias_hit or {}).get("name_zh")
    if not name_zh:
        return None
    aliases = []
    if alias_hit:
        aliases.extend(alias_hit.get("aliases") or [])
    for alias in item.get("aliases") or []:
        alias_text = str(alias).strip()
        if alias_text and re.search(r"[\u4e00-\u9fff]", alias_text):
            aliases.append(alias_text)
    deduped: list[str] = []
    for alias in aliases:
        if alias and alias != name_zh and alias not in deduped:
            deduped.append(alias)
    return {
        "name": name_zh,
        "aliases": deduped[:12],
        "status": "curated" if alias_hit else "imported_existing",
        "source": "drug_zh_aliases.csv" if alias_hit else "substance.name_zh",
    }
