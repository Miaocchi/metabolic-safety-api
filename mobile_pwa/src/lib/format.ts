import type { JournalEntry, RiskLevel, SubstanceSummary } from "../types";

export const riskLabels: Record<string, string> = {
  Contraindicated: "禁忌",
  Dangerous: "高危",
  Unsafe: "不安全",
  Major: "严重",
  Moderate: "中度",
  Synergy: "协同/增强",
  Minor: "轻微",
  "Low Risk": "低风险",
  NoKnownClinicalSignificance: "无明确临床意义",
  Unknown: "未知",
};

export const riskRank: Record<string, number> = {
  Contraindicated: 7,
  Dangerous: 6,
  Unsafe: 6,
  Major: 5,
  Moderate: 4,
  Synergy: 3,
  Minor: 2,
  "Low Risk": 1,
  Unknown: 1,
  NoKnownClinicalSignificance: 0,
};

export function normalizeText(value: unknown) {
  return String(value || "")
    .toLocaleLowerCase("zh-CN")
    .normalize("NFKC")
    .replace(/[\s_\-./()[\]{}]+/g, " ")
    .trim();
}

export function compactText(value: unknown) {
  return normalizeText(value).replace(/\s+/g, "");
}

export function aliasesOf(item?: Partial<SubstanceSummary>) {
  if (!item) return [];
  if (Array.isArray(item.aliases)) return item.aliases.filter(Boolean).map(String);
  return [];
}

export function displayName(item?: Partial<SubstanceSummary>) {
  return item?.name_zh || item?.name_en || item?.id || "未命名物质";
}

export function subName(item?: Partial<SubstanceSummary>) {
  const zh = item?.name_zh || "";
  const en = item?.name_en || "";
  if (zh && en && zh !== en) return en;
  return item?.id || "";
}

export function haystack(item?: Partial<SubstanceSummary>) {
  return normalizeText([item?.id, item?.name_zh, item?.name_en, item?.category, ...aliasesOf(item)].filter(Boolean).join(" "));
}

export function scoreItem(item: SubstanceSummary, query: string) {
  const q = normalizeText(query);
  const qCompact = compactText(query);
  if (!q) return 1;
  const id = normalizeText(item.id);
  const en = normalizeText(item.name_en);
  const zh = normalizeText(item.name_zh);
  const bag = haystack(item);
  const compactBag = compactText(bag);
  if (id === q || en === q || zh === q) return 100;
  if (compactText(id) === qCompact || compactText(en) === qCompact || compactText(zh) === qCompact) return 95;
  if (id.startsWith(q) || en.startsWith(q) || zh.startsWith(q)) return 80;
  if (bag.includes(q) || compactBag.includes(qCompact)) return 50;
  return 0;
}

export function searchShardKey(value: string) {
  const text = compactText(value);
  if (!text) return "other";
  const codePoint = text.codePointAt(0);
  if (!codePoint) return "other";
  const char = String.fromCodePoint(codePoint);
  if (/^[a-z0-9]$/i.test(char)) {
    const prefix = Array.from(text).filter((part) => /^[a-z0-9]$/i.test(part)).join("").slice(0, 2);
    return (prefix || char).toLocaleLowerCase("en-US");
  }
  return `u${codePoint.toString(16).padStart(4, "0")}`;
}

export function searchShardKeysForQuery(query: string) {
  const normalized = normalizeText(query);
  const compact = compactText(query);
  const terms = [normalized, ...normalized.split(" ").filter(Boolean)];
  if (compact && compact !== normalized) terms.push(compact);
  if (compact && !/^[\x00-\x7F]+$/.test(compact)) terms.push(...Array.from(compact).slice(0, 4));
  const keys: string[] = [];
  const seen = new Set<string>();
  for (const term of terms) {
    const key = searchShardKey(term);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    keys.push(key);
    if (keys.length >= 6) break;
  }
  return keys.length ? keys : ["other"];
}

export function formatNumber(value: number, fraction = 0) {
  return Number(value || 0).toLocaleString("zh-CN", {
    maximumFractionDigits: fraction,
    minimumFractionDigits: fraction,
  });
}

export function formatHours(value: unknown) {
  if (value === null || value === undefined || value === "") return "未知";
  const numeric = Number(value);
  if (Number.isFinite(numeric)) return `${numeric.toFixed(2)} h`;
  return String(value);
}

export function riskClass(level?: RiskLevel) {
  return String(level || "Unknown").toLocaleLowerCase("en-US").replace(/[^a-z0-9]+/g, "-");
}

export function riskLabel(level?: RiskLevel) {
  return riskLabels[String(level || "Unknown")] || String(level || "未知");
}

export function riskSortValue(level?: RiskLevel) {
  return riskRank[String(level || "Unknown")] ?? 1;
}

export function toDateTimeLocal(timestamp: number) {
  const date = new Date(timestamp);
  const offsetMs = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

export function dateTimeLocalToTimestamp(value: string) {
  const timestamp = new Date(value).getTime();
  return Number.isFinite(timestamp) ? timestamp : Date.now();
}

export function routeLabel(value?: string) {
  return {
    Oral: "口服",
    Sublingual: "舌下",
    Insufflated: "鼻腔",
    Topical: "经皮",
    IV: "静脉/瞬时",
    Other: "其他",
  }[value || ""] || value || "未记录";
}

export function stomachLabel(value?: string) {
  return {
    Fasting: "完全空腹",
    Light: "正常/少量进食",
    Heavy: "高脂重餐",
  }[value || ""] || value || "未记录";
}

export function formatJournalEntry(entry: JournalEntry) {
  return `${entry.dosage} ${entry.unit} · ${routeLabel(entry.route)} · ${stomachLabel(entry.stomachState)}`;
}

export function clippedText(value: unknown, max = 240) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (text.length <= max) return text;
  return `${text.slice(0, max - 1)}...`;
}
