/**
 * @module domain/risk
 *
 * Pure domain helpers for risk event construction and classification.
 * These functions have no side effects and no dependency on IndexedDB or network.
 */

import type { InteractionRow, RiskEvent, RiskLevel } from "../types";
import { riskSeverity, isCandidateTier, sourceTierRank, type InteractionKind } from "./safety";

// ── Risk event construction helpers ───────────────────────────────────

export interface RiskEventDraft {
  id: string;
  kind: InteractionKind;
  level: RiskLevel | string;
  title: string;
  subtitle?: string;
  note?: string;
  source?: string;
  sourceTier?: string;
  confidence?: string;
}

/**
 * Validates that a risk event draft has minimum required fields.
 */
export function validateRiskEventDraft(draft: RiskEventDraft): string[] {
  const errors: string[] = [];
  if (!draft.id?.trim()) errors.push("Risk event requires an id.");
  if (!draft.kind) errors.push("Risk event requires a kind.");
  if (!draft.title?.trim()) errors.push("Risk event requires a title.");
  return errors;
}

/**
 * Determines whether a risk from a candidate/weak source tier should be
 * allowed to override or downgrade an existing risk from a higher tier.
 *
 * Policy: Community and Signal sources must NOT downgrade higher-tier risks.
 */
export function shouldApplyCandidateRisk(
  candidateTier: string | undefined,
  existingTier: string | undefined,
): boolean {
  if (!isCandidateTier(candidateTier)) return true;
  // Candidate tiers only apply if there's no existing risk or existing is also candidate
  if (!existingTier) return true;
  return isCandidateTier(existingTier);
}

/**
 * Merges two risk events, preferring the one with higher authority.
 * If tiers are equal, prefers the one with higher severity.
 */
export function mergeRiskEvents(existing: RiskEvent, incoming: RiskEvent): RiskEvent {
  const existingTierRank = sourceTierRank(existing.sourceTier);
  const incomingTierRank = sourceTierRank(incoming.sourceTier);
  if (incomingTierRank > existingTierRank) return incoming;
  if (incomingTierRank < existingTierRank) return existing;
  // Same tier — prefer higher severity
  return riskSeverity(incoming.level) > riskSeverity(existing.level) ? incoming : existing;
}

/**
 * Deduplicates risk events by id, keeping the highest-authority version.
 */
export function deduplicateRisks(risks: RiskEvent[]): RiskEvent[] {
  const byId = new Map<string, RiskEvent>();
  for (const risk of risks) {
    const existing = byId.get(risk.id);
    if (!existing) {
      byId.set(risk.id, risk);
    } else {
      byId.set(risk.id, mergeRiskEvents(existing, risk));
    }
  }
  return [...byId.values()];
}

/**
 * Sorts risk events by severity (descending), then by title (ascending, zh-CN).
 */
export function sortRisksBySeverity(risks: RiskEvent[]): RiskEvent[] {
  return [...risks].sort(
    (a, b) => riskSeverity(b.level) - riskSeverity(a.level) || a.title.localeCompare(b.title, "zh-CN"),
  );
}

/**
 * Filters risks to only those above a severity threshold.
 */
export function filterHighRisks(risks: RiskEvent[], minLevel: RiskLevel | string = "Major"): RiskEvent[] {
  const threshold = riskSeverity(minLevel);
  return risks.filter((risk) => riskSeverity(risk.level) >= threshold);
}

/**
 * Counts risks by category for summary display.
 */
export function riskSummary(risks: RiskEvent[]): {
  total: number;
  critical: number;
  warning: number;
  unknown: number;
  highRiskCount: number;
} {
  let critical = 0;
  let warning = 0;
  let unknown = 0;
  for (const risk of risks) {
    const severity = riskSeverity(risk.level);
    if (!risk.level || risk.level === "Unknown") {
      unknown++;
    } else if (severity >= 5) {
      critical++;
    } else if (severity >= 3) {
      warning++;
    }
  }
  return {
    total: risks.length,
    critical,
    warning,
    unknown,
    highRiskCount: critical,
  };
}

// ── Interaction row helpers ───────────────────────────────────────────

/**
 * Builds a display title from an interaction row.
 */
export function interactionTitle(row: InteractionRow): string {
  return [
    row.substance_a_name || row.substance_a_name_en || row.substance_a_id,
    row.substance_b_name || row.substance_b_name_en || row.substance_b_id,
  ]
    .filter(Boolean)
    .join(" / ");
}

/**
 * Builds a display subtitle from an interaction row.
 */
export function interactionSubtitle(row: InteractionRow): string {
  return row.action || row.interaction_type || "相互作用";
}

/**
 * Returns the effective risk level from an interaction row,
 * preserving Unknown when data is insufficient.
 */
export function interactionEffectiveLevel(row: InteractionRow): RiskLevel {
  return row.risk_level || "Unknown";
}

/**
 * Returns the interaction kind based on conflict_status.
 */
export function interactionKind(row: InteractionRow): InteractionKind {
  return row.conflict_status ? "conflict" : "interaction";
}
