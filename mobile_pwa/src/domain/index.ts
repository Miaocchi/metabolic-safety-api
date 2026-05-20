/**
 * @module domain
 *
 * Domain layer barrel export.
 * Pure domain types and helpers — no side effects, no IndexedDB, no network.
 */
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
