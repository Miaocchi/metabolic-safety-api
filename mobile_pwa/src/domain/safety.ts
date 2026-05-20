/**
 * @module domain/safety
 *
 * Core safety domain types and invariants.
 *
 * CRITICAL INVARIANT: "Unknown" ≠ "Safe"
 *   - Unknown means insufficient data to assess; it must never be rendered as "safe" or "no concern."
 *   - NoKnownClinicalSignificance is the only level meaning "no known clinical significance."
 *
 * Source tier hierarchy (descending authority):
 *   Regulatory > Guideline > Curated > Reviewed > Signal > Community > LocalModel
 *
 * Community and Signal tiers are candidate/coverage-gap data only.
 * They must NOT downgrade higher-tier risks.
 */

// ── Source tier hierarchy ─────────────────────────────────────────────

export const SOURCE_TIERS = [
  "Regulatory",
  "Guideline",
  "Curated",
  "Reviewed",
  "Signal",
  "Community",
  "LocalModel",
] as const;

export type SourceTier = (typeof SOURCE_TIERS)[number];

/**
 * Returns a numeric authority rank for a source tier.
 * Higher number = more authoritative.
 */
export function sourceTierRank(tier?: string): number {
  const index = SOURCE_TIERS.indexOf(tier as SourceTier);
  return index >= 0 ? SOURCE_TIERS.length - index : 0;
}

/**
 * Returns true if the tier is a candidate/weak source (Signal or Community).
 * These tiers must not downgrade higher-tier risks.
 */
export function isCandidateTier(tier?: string): boolean {
  return tier === "Signal" || tier === "Community";
}

/**
 * Returns true if the given tier is at least as authoritative as the minimum.
 */
export function tierMeetsMinimum(tier: string | undefined, minimum: SourceTier): boolean {
  return sourceTierRank(tier) >= sourceTierRank(minimum);
}

// ── Risk level classification ─────────────────────────────────────────

export const RISK_LEVELS = [
  "Contraindicated",
  "Dangerous",
  "Unsafe",
  "Major",
  "Moderate",
  "Synergy",
  "Minor",
  "Low Risk",
  "NoKnownClinicalSignificance",
  "Unknown",
] as const;

export type DomainRiskLevel = (typeof RISK_LEVELS)[number];

/**
 * Severity rank for risk levels.
 * Higher = more severe.
 *
 * CRITICAL: Unknown=1 (not 0) because Unknown ≠ Safe.
 * NoKnownClinicalSignificance=0 is the only "no concern" level.
 */
export const RISK_SEVERITY: Record<string, number> = {
  Contraindicated: 7,
  Dangerous: 6,
  Unsafe: 6,
  Major: 5,
  Moderate: 4,
  Synergy: 3,
  Minor: 2,
  "Low Risk": 1,
  Unknown: 1, // NOT 0 — Unknown ≠ Safe
  NoKnownClinicalSignificance: 0,
};

export function riskSeverity(level?: string): number {
  return RISK_SEVERITY[level ?? "Unknown"] ?? 1;
}

/**
 * Returns true if the level represents a known-safe condition.
 * ONLY NoKnownClinicalSignificance qualifies.
 */
export function isKnownSafe(level?: string): boolean {
  return level === "NoKnownClinicalSignificance";
}

/**
 * Returns true if the level is Unknown — meaning data is insufficient.
 * Unknown must never be displayed as safe.
 */
export function isUnknownRisk(level?: string): boolean {
  return !level || level === "Unknown";
}

/**
 * Returns true if the level represents a clinically significant risk
 * (i.e., not Unknown and not NoKnownClinicalSignificance).
 */
export function isClinicallySignificant(level?: string): boolean {
  return !isUnknownRisk(level) && !isKnownSafe(level);
}

/**
 * Returns true if the level is high severity (≥ Major).
 */
export function isHighSeverity(level?: string): boolean {
  return riskSeverity(level) >= RISK_SEVERITY.Major;
}

/**
 * Classifies a risk level into a UI category for display.
 */
export type RiskCategory = "critical" | "warning" | "info" | "unknown" | "safe";

export function categorizeRisk(level?: string): RiskCategory {
  if (isKnownSafe(level)) return "safe";
  if (isUnknownRisk(level)) return "unknown";
  const severity = riskSeverity(level);
  if (severity >= 5) return "critical"; // Major and above
  if (severity >= 3) return "warning";  // Synergy, Moderate
  return "info";                        // Minor, Low Risk
}

// ── Conflict / interaction kind classification ────────────────────────

export type InteractionKind = "conflict" | "interaction" | "dose" | "overdose" | "signal" | "model";

/**
 * Classifies a risk event into a human-readable kind label (in Chinese).
 */
export function interactionKindLabel(kind?: string): string {
  switch (kind) {
    case "conflict": return "冲突";
    case "interaction": return "相互作用";
    case "dose":
    case "overdose": return "过量";
    case "signal": return "警戒信号";
    case "model": return "模型提示";
    default: return "相互作用";
  }
}

// ── Safety note constants ─────────────────────────────────────────────

export const SAFETY_NOTES = {
  unknownNotSafe: "Unknown 表示资料不足，不能显示为安全。",
  communityCandidate: "社区数据仅为候选/覆盖缺口，不降低更高层级风险。",
  signalCandidate: "药物警戒自发报告信号不代表因果关系、发生率或确认联用冲突。",
  localModelOnly: "移动端模型用于趋势估算，不是临床剂量建议。",
  doseNormalization: "自动归一化剂量规则需要结合人群、途径、适应症和制剂复核。",
  notClinicalDecision: "这是个人日志和趋势估算，不是临床决策支持。",
  /** Label sections are evidence text excerpts, not clinical instructions. */
  labelTextEvidence: "标签文段为证据摘录，不是临床用药指导。",
  /** Safety warnings are machine-extracted; must not override higher-trust curated rules. */
  safetyWarningExtraction: "安全警告为机器提取标签文段，不能替代更高层级的人工审核规则。",
  /** Interaction signals are label-derived, do not replace DDInter risk rules. */
  interactionSignalReview: "交互信号来源于标签摘录，需人工复核，不能替代 DDInter 风险规则。",
  /**
   * FooDrugs food interactions are text-mined, low-confidence, non-causal.
   * Must NOT downgrade regulatory or curated evidence.
   */
  foodInteractionCandidate: "FooDrugs 食物/生物活性物候选信号为低置信度文本挖掘，不代表因果关系，不能替代监管或人工审核证据。",
  /**
   * OnSIDES adverse signals are label-derived, not incidence or causality.
   */
  adverseSignalNotIncidence: "OnSIDES 不良信号来源于标签文本挖掘，不代表发生率或因果关系，仅作低置信度复核参考。",
  /**
   * PGx rows are evidence-only; not individualized prescribing recommendations.
   */
  pgxEvidenceOnly: "PGx 行为 PharmGKB/ClinPGx 证据展示，不是个体化处方建议。Unknown ≠ 安全。",
} as const;
