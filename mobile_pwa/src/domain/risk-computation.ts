/**
 * @module domain/risk-computation
 *
 * Pure domain helpers for computing risk events from journal entries,
 * substance bundles, and signal rows.
 * No side effects, no IndexedDB, no network.
 *
 * Canonical source — `lib/risks.ts` re-exports this module for backward compat.
 */
import type { DoseRule, InteractionRow, JournalEntry, RiskEvent, SubstanceBundle, UserProfile } from "../types";
import { displayName, riskSortValue } from "./format";
import { doseInMg } from "./pk";

type SignalRow = {
  risk_kind?: string;
  signal_id?: string;
  substance_id?: string;
  substance_name?: string;
  query_term?: string;
  reactions?: Array<{ reaction?: string; label?: string; count?: number }>;
  risk_level?: string;
  confidence?: string;
  source_tier?: string;
  interaction_type?: string;
  source_name?: string;
  source_url?: string;
  note?: string;
};

function signalReportStats(row: SignalRow) {
  const counts = (Array.isArray(row.reactions) ? row.reactions : [])
    .map((item) => Number(item.count || 0))
    .filter((count) => Number.isFinite(count) && count > 0);
  return {
    total: counts.reduce((sum, count) => sum + count, 0),
    max: counts.length ? Math.max(...counts) : 0,
  };
}

function signalRiskLevel(row: SignalRow) {
  const level = row.risk_level || "Minor";
  const { total, max } = signalReportStats(row);
  if (level === "Moderate" && max > 0 && max < 20 && total < 50) return "Minor";
  return level;
}

function routeMatches(entry: JournalEntry, rule: DoseRule) {
  const route = String(rule.route || "").trim().toLowerCase();
  if (!route || ["any", "all", "unspecified", "unknown"].includes(route)) return true;
  const entryRoute = String(entry.route || "").trim().toLowerCase();
  if (!entryRoute || entryRoute === "other") return true;
  const aliases: Record<string, string[]> = {
    oral: ["oral", "po", "by mouth"],
    sublingual: ["sublingual"],
    insufflated: ["insufflated", "intranasal", "nasal"],
    topical: ["topical", "transdermal"],
    iv: ["iv", "intravenous"],
  };
  return (aliases[entryRoute] || [entryRoute]).some((alias) => route === alias || route.includes(alias));
}

function sameUnit(entry: JournalEntry, rule: DoseRule) {
  return String(rule.unit || "mg").toLowerCase() === String(entry.unit || "mg").toLowerCase() || String(rule.unit || "mg").toLowerCase() === "mg";
}

export function doseRuleRisks(entries: JournalEntry[], bundles: Record<string, SubstanceBundle>) {
  const risks: RiskEvent[] = [];
  for (const entry of entries) {
    const bundle = bundles[entry.substanceId];
    if (!bundle) continue;
    for (const rule of bundle.doseRules || []) {
      if (!routeMatches(entry, rule) || !sameUnit(entry, rule)) continue;
      const windowHours = Number(rule.window_hours || 24);
      const windowStart = entry.timestamp - windowHours * 3600000;
      const related = entries.filter((candidate) => candidate.substanceId === entry.substanceId && candidate.timestamp >= windowStart && candidate.timestamp <= entry.timestamp);
      const totalMg = related.reduce((sum, candidate) => sum + doseInMg(candidate), 0);
      for (const threshold of rule.thresholds || []) {
        const limit = Number(threshold.limit || 0);
        if (!limit) continue;
        const amount = threshold.kind === "single" ? doseInMg(entry) : totalMg;
        if (amount < limit) continue;
        risks.push({
          id: `dose:${rule.rule_id || entry.id}:${threshold.kind}:${limit}`,
          kind: "dose",
          level: threshold.level || "Unknown",
          title: `${entry.substanceName} 剂量阈值`,
          subtitle: threshold.label || `${amount.toFixed(0)} mg / ${windowHours}h`,
          note: rule.note || "自动归一化剂量规则需要结合人群、途径、适应症和制剂复核。",
          source: rule.source_name,
          sourceTier: rule.source_tier,
          confidence: rule.confidence,
          entries: related,
        });
      }
    }
  }
  return dedupeRisks(risks);
}

export function localInteractionRisks(rows: InteractionRow[], entries: JournalEntry[]) {
  return rows.map((row) => ({
      id: `interaction:${row.interaction_id || row.substance_a_id || ""}:${row.substance_b_id || ""}`,
      kind: "interaction",
      level: row.risk_level || "Unknown",
    title: [row.substance_a_name || row.substance_a_name_en || row.substance_a_id, row.substance_b_name || row.substance_b_name_en || row.substance_b_id]
      .filter(Boolean)
      .join(" / "),
    subtitle: row.action || row.interaction_type || "相互作用",
    note: row.note || row.mechanism || "本地后台返回的活跃窗口相互作用。",
    source: row.source_name || row.remote_source,
    sourceTier: row.source_tier,
    confidence: row.confidence,
    entries,
  })) satisfies RiskEvent[];
}

export function localStaticPairRisks(entries: JournalEntry[], bundles: Record<string, SubstanceBundle>) {
  const risks: RiskEvent[] = [];
  for (let i = 0; i < entries.length; i += 1) {
    for (let j = i + 1; j < entries.length; j += 1) {
      const a = entries[i];
      const b = entries[j];
      const interactions = bundles[a.substanceId]?.interactions || [];
      const hit = interactions.find((row) => row.substance_a_id === b.substanceId || row.substance_b_id === b.substanceId);
      if (!hit) continue;
      risks.push({
        id: `pair:${hit.interaction_id || a.id + b.id}`,
        kind: hit.conflict_status ? "conflict" : "interaction",
        level: hit.risk_level || "Unknown",
        title: `${a.substanceName} / ${b.substanceName}`,
        subtitle: hit.action || hit.interaction_type || "相互作用",
        note: hit.note || hit.mechanism || "来自静态 API 的本地缓存相互作用。",
        source: hit.source_name || hit.remote_source,
        sourceTier: hit.source_tier,
        confidence: hit.confidence,
        entries: [a, b],
      });
    }
  }
  return dedupeRisks(risks);
}

export function overdoseEvidenceRisks(entries: JournalEntry[], bundles: Record<string, SubstanceBundle>) {
  return entries.flatMap((entry) => {
    const bundle = bundles[entry.substanceId];
    if (!bundle?.overdoseWarnings?.length) return [];
    return [{
      id: `overdose:${entry.substanceId}`,
      kind: "overdose",
      level: "Unknown",
      title: `${displayName(bundle.detail)} 有过量警告文本`,
      subtitle: `${bundle.overdoseWarnings.length} 条来源证据`,
      note: "此项不代表当前剂量已过量，只提示详情页存在监管标签过量段落。Unknown 不能当作安全。",
      source: bundle.overdoseWarnings[0]?.source_name,
      sourceTier: bundle.overdoseWarnings[0]?.source_tier,
      confidence: bundle.overdoseWarnings[0]?.confidence,
      entries: [entry],
    } satisfies RiskEvent];
  });
}

export function modelRisks(entries: JournalEntry[], bundles: Record<string, SubstanceBundle>, profile: UserProfile) {
  return entries.flatMap((entry) => {
    const doseMgKg = doseInMg(entry) / Math.max(profile.weightKg || 70, 1);
    if (doseMgKg < 15 && profile.coreTempC < 39 && profile.sleepDebtHours < 24) return [];
    return [{
      id: `model:${entry.id}`,
      kind: "model",
      level: doseMgKg >= 40 || profile.coreTempC >= 39.5 ? "Moderate" : "Minor",
      title: `${entry.substanceName} 个体暴露提示`,
      subtitle: `${doseMgKg.toFixed(1)} mg/kg · 体温 ${profile.coreTempC}°C · 睡眠不足 ${profile.sleepDebtHours}h`,
      note: "移动端模型用于趋势估算，不是临床剂量建议。",
      source: "PWA PopPK trend model",
      sourceTier: "LocalModel",
      confidence: "Low",
      entries: [entry],
    } satisfies RiskEvent];
  });
}

export function adverseSignalRisks(rows: unknown[], entries: JournalEntry[]) {
  const byId = new Map(entries.map((entry) => [entry.substanceId, entry]));
  return (rows as SignalRow[]).flatMap((row) => {
    if (!row || row.risk_kind !== "signal") return [];
    const entry = row.substance_id ? byId.get(row.substance_id) : undefined;
    const reactions = Array.isArray(row.reactions) ? row.reactions : [];
    const reactionText = reactions.length
      ? reactions.map((item) => `${item.label || item.reaction || "事件"} ${Number(item.count || 0).toLocaleString("zh-CN")} 例`).join("；")
      : row.query_term ? `按 ${row.query_term} 检索` : "公开药物警戒候选信号";
    return [{
      id: `signal:${row.signal_id || row.substance_id || reactionText}`,
      kind: "signal",
      level: signalRiskLevel(row),
      title: `${row.substance_name || entry?.substanceName || row.substance_id || "药物"} 药物警戒候选信号`,
      subtitle: reactionText,
      note: row.note || "FAERS 自发不良事件报告只提示共报告候选信号，不代表因果关系、发生率或确认联用冲突。",
      source: row.source_name || "openFDA FAERS adverse event",
      sourceTier: row.source_tier || "Signal",
      confidence: row.confidence || "Low",
      entries: entry ? [entry] : [],
      reactions,
    } satisfies RiskEvent];
  });
}

export function sortRisks(risks: RiskEvent[]) {
  return [...risks].sort((a, b) => riskSortValue(b.level) - riskSortValue(a.level) || a.title.localeCompare(b.title, "zh-CN"));
}

function dedupeRisks(risks: RiskEvent[]) {
  return [...new Map(risks.map((risk) => [risk.id, risk])).values()];
}
