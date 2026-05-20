/**
 * @module services/risk-service
 *
 * Domain service façade for risk computation.
 * Wraps existing risk functions from lib/risks.ts with domain-layer
 * safety semantics (Unknown ≠ Safe, candidate tier handling).
 */
import type { JournalEntry, RiskEvent, SubstanceBundle, UserProfile } from "../types";
import type { ApiClient } from "../lib/api";
import {
  doseRuleRisks,
  localInteractionRisks,
  localStaticPairRisks,
  modelRisks,
  overdoseEvidenceRisks,
  adverseSignalRisks,
  sortRisks as legacySortRisks,
} from "../lib/risks";
import { deduplicateRisks, sortRisksBySeverity, riskSummary, filterHighRisks } from "../domain/risk";
import { isUnknownRisk } from "../domain/safety";

// ── Types ─────────────────────────────────────────────────────────────

export interface RiskComputationInput {
  entries: JournalEntry[];
  bundles: Record<string, SubstanceBundle>;
  profile: UserProfile;
  signalRows?: unknown[];
}

export interface RiskComputationResult {
  risks: RiskEvent[];
  highRisks: RiskEvent[];
  summary: ReturnType<typeof riskSummary>;
  hasUnknownRisks: boolean;
}

// ── RiskService ───────────────────────────────────────────────────────

export class RiskService {
  private readonly api: ApiClient;

  constructor(api: ApiClient) {
    this.api = api;
  }

  /**
   * Computes all risk events from the current journal state.
   * Combines static pair interactions, dose rules, overdose evidence,
   * model-based risks, and adverse signal risks.
   *
   * Preserves Unknown semantics: Unknown risks are included and never
   * treated as safe.
   */
  computeRisks(input: RiskComputationInput): RiskComputationResult {
    const { entries, bundles, profile, signalRows } = input;

    const rawRisks = [
      ...localStaticPairRisks(entries, bundles),
      ...doseRuleRisks(entries, bundles),
      ...overdoseEvidenceRisks(entries, bundles),
      ...modelRisks(entries, bundles, profile),
      ...(signalRows ? adverseSignalRisks(signalRows, entries) : []),
    ];

    // Deduplicate by id, keeping highest-authority version
    const risks = sortRisksBySeverity(deduplicateRisks(rawRisks));
    const highRisks = filterHighRisks(risks, "Major");
    const summary = riskSummary(risks);
    const hasUnknownRisks = risks.some((r) => isUnknownRisk(r.level));

    return { risks, highRisks, summary, hasUnknownRisks };
  }

  /**
   * Fetches adverse signal data for active substances.
   *
   * Only performs live openFDA fallback when `liveFallback` is explicitly
   * true (requires user consent), because the live endpoint transmits
   * substance names/aliases to a third-party service.
   */
  async fetchAdverseSignals(
    signalItems: Array<{ id: string; name_en?: string; name_zh?: string; aliases?: string[] }>,
    limit = 3,
    options: { liveFallback?: boolean } = {},
  ): Promise<unknown[]> {
    return this.api.adverseSignals(signalItems, limit, options);
  }

  /**
   * Converts raw adverse signal rows into RiskEvent objects.
   */
  buildSignalRisks(signalRows: unknown[], entries: JournalEntry[]): RiskEvent[] {
    return adverseSignalRisks(signalRows, entries);
  }

  /**
   * Computes local interaction risks from API-returned rows.
   */
  computeLocalInteractionRisks(rows: Parameters<typeof localInteractionRisks>[0], entries: JournalEntry[]): RiskEvent[] {
    return localInteractionRisks(rows, entries);
  }
}
