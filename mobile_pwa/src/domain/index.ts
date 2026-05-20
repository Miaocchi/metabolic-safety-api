/**
 * @module domain
 *
 * Domain layer barrel export.
 * Pure domain types and helpers — no side effects, no IndexedDB, no network.
 */

// ── Safety classification ─────────────────────────────────────────────
export {
  SOURCE_TIERS,
  RISK_LEVELS,
  RISK_SEVERITY,
  SAFETY_NOTES,
  type SourceTier,
  type DomainRiskLevel,
  type RiskCategory,
  type InteractionKind,
  sourceTierRank,
  isCandidateTier,
  tierMeetsMinimum,
  riskSeverity,
  isKnownSafe,
  isUnknownRisk,
  isClinicallySignificant,
  isHighSeverity,
  categorizeRisk,
  interactionKindLabel,
} from "./safety";

// ── Risk event construction ───────────────────────────────────────────
export {
  validateRiskEventDraft,
  shouldApplyCandidateRisk,
  mergeRiskEvents,
  deduplicateRisks,
  sortRisksBySeverity,
  filterHighRisks,
  riskSummary,
  interactionTitle,
  interactionSubtitle,
  interactionEffectiveLevel,
  interactionKind,
  type RiskEventDraft,
} from "./risk";

// ── Risk computation (migrated from lib/risks) ────────────────────────
export {
  doseRuleRisks,
  localInteractionRisks,
  localStaticPairRisks,
  overdoseEvidenceRisks,
  modelRisks,
  adverseSignalRisks,
  sortRisks,
} from "./risk-computation";

// ── Formatting & display (migrated from lib/format) ───────────────────
export {
  riskLabels,
  riskRank,
  normalizeText,
  compactText,
  aliasesOf,
  displayName,
  subName,
  haystack,
  scoreItem,
  searchShardKey,
  searchShardKeysForQuery,
  formatNumber,
  formatHours,
  riskClass,
  riskLabel,
  riskSortValue,
  toDateTimeLocal,
  dateTimeLocalToTimestamp,
  routeLabel,
  stomachLabel,
  formatJournalEntry,
  clippedText,
} from "./format";

// ── Pharmacokinetic model (migrated from lib/pk) ──────────────────────
export {
  defaultProfile,
  type CurvePoint,
  type CurveSeries,
  type CurveModel,
  doseInMg,
  substanceDetailForModel,
  observedBaselineHalfLifeHours,
  baselineHalfLifeHours,
  baselineDurationMinutes,
  adjustedPkParams,
  concentrationAt,
  activeEntries,
  calculatePMI,
  pmiLabel,
  exposureMetricsForEntry,
  forwardExposureMetricsForEntry,
  entryHasMeaningfulExposure,
  meaningfulExposureEntries,
  forwardExposureIndex,
  type ForwardExposureGroup,
  forwardExposureGroups,
  type PmiResult,
  calculateFullPMI,
  buildCurveModel,
} from "./pk";
