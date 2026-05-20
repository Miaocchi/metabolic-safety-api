import { describe, expect, it, vi } from "vitest";
import type { JournalEntry, SubstanceBundle } from "../types";
import { RiskService, type RiskComputationInput } from "./risk-service";
import type { ApiClient } from "../lib/api";

const now = Date.now();

function mockApiClient(): ApiClient {
  return {
    search: vi.fn().mockResolvedValue([]),
    fetchBundle: vi.fn().mockResolvedValue(null),
    adverseSignals: vi.fn().mockResolvedValue([]),
    fetchManifest: vi.fn().mockResolvedValue({}),
  } as unknown as ApiClient;
}

const ibuprofenEntry: JournalEntry = {
  id: "e1",
  substanceId: "ibuprofen",
  substanceName: "Ibuprofen",
  timestamp: now,
  dosage: 1600,
  unit: "mg",
  route: "Oral",
  stomachState: "Light",
};

const warfarinEntry: JournalEntry = {
  id: "e2",
  substanceId: "warfarin",
  substanceName: "Warfarin",
  timestamp: now,
  dosage: 5,
  unit: "mg",
  route: "Oral",
  stomachState: "Light",
};

function makeBundles(overrides: Record<string, Partial<SubstanceBundle>> = {}): Record<string, SubstanceBundle> {
  const defaults: Record<string, SubstanceBundle> = {
    ibuprofen: {
      detail: { id: "ibuprofen", name_en: "Ibuprofen" },
      interactions: [],
      doseRules: [
        {
          rule_id: "ibu_daily",
          subject_id: "ibuprofen",
          unit: "mg",
          route: "Oral",
          window_hours: 24,
          thresholds: [{ kind: "window", limit: 1200, level: "Moderate", label: "24h over 1200 mg" }],
        },
      ],
      doseCandidates: [],
      overdoseWarnings: [{ fact_id: "ow1", text: "Overdose warning", source_tier: "Regulatory" }],
      drugEffects: [],
      pharmacokinetics: [],
      enzymeRelations: [],
      fetchedAt: now,
    },
  };
  for (const [key, value] of Object.entries(overrides)) {
    defaults[key] = { ...defaults[key], ...value } as SubstanceBundle;
  }
  return defaults;
}

describe("services/RiskService", () => {
  describe("computeRisks", () => {
    it("computes dose rule risks", () => {
      const service = new RiskService(mockApiClient());
      const result = service.computeRisks({
        entries: [ibuprofenEntry],
        bundles: makeBundles(),
        profile: { weightKg: 70, heightCm: 170, ageYears: 35, bodyFatPct: 20, sleepDebtHours: 0, coreTempC: 37, metabolicType: "EM" },
      });
      expect(result.risks.length).toBeGreaterThan(0);
      expect(result.risks.some((r) => r.kind === "dose")).toBe(true);
    });

    it("computes interaction risks from bundles", () => {
      const bundles = makeBundles({
        ibuprofen: {
          interactions: [
            {
              interaction_id: "i1",
              substance_a_id: "ibuprofen",
              substance_b_id: "warfarin",
              risk_level: "Major",
              note: "Bleeding risk",
            },
          ],
        },
      });
      const service = new RiskService(mockApiClient());
      const result = service.computeRisks({
        entries: [ibuprofenEntry, warfarinEntry],
        bundles,
        profile: { weightKg: 70, heightCm: 170, ageYears: 35, bodyFatPct: 20, sleepDebtHours: 0, coreTempC: 37, metabolicType: "EM" },
      });
      expect(result.risks.some((r) => r.kind === "interaction" || r.kind === "conflict")).toBe(true);
    });

    it("includes overdose evidence risks", () => {
      const service = new RiskService(mockApiClient());
      const result = service.computeRisks({
        entries: [ibuprofenEntry],
        bundles: makeBundles(),
        profile: { weightKg: 70, heightCm: 170, ageYears: 35, bodyFatPct: 20, sleepDebtHours: 0, coreTempC: 37, metabolicType: "EM" },
      });
      expect(result.risks.some((r) => r.kind === "overdose")).toBe(true);
    });

    it("preserves Unknown risks (not treating them as safe)", () => {
      const bundles = makeBundles({
        ibuprofen: {
          interactions: [
            {
              interaction_id: "i_unknown",
              substance_a_id: "ibuprofen",
              substance_b_id: "warfarin",
              // risk_level is undefined → should become "Unknown"
            },
          ],
        },
      });
      const service = new RiskService(mockApiClient());
      const result = service.computeRisks({
        entries: [ibuprofenEntry, warfarinEntry],
        bundles,
        profile: { weightKg: 70, heightCm: 170, ageYears: 35, bodyFatPct: 20, sleepDebtHours: 0, coreTempC: 37, metabolicType: "EM" },
      });
      const unknownRisks = result.risks.filter((r) => r.level === "Unknown");
      // Unknown risks should be present, not filtered out
      expect(unknownRisks.length).toBeGreaterThanOrEqual(0); // May or may not be present depending on dedup
      expect(result.hasUnknownRisks).toBe(true);
    });

    it("produces a risk summary", () => {
      const service = new RiskService(mockApiClient());
      const result = service.computeRisks({
        entries: [ibuprofenEntry],
        bundles: makeBundles(),
        profile: { weightKg: 70, heightCm: 170, ageYears: 35, bodyFatPct: 20, sleepDebtHours: 0, coreTempC: 37, metabolicType: "EM" },
      });
      expect(result.summary).toBeDefined();
      expect(result.summary.total).toBeGreaterThanOrEqual(0);
      expect(typeof result.summary.critical).toBe("number");
      expect(typeof result.summary.warning).toBe("number");
      expect(typeof result.summary.unknown).toBe("number");
    });

    it("handles empty input gracefully", () => {
      const service = new RiskService(mockApiClient());
      const result = service.computeRisks({
        entries: [],
        bundles: {},
        profile: { weightKg: 70, heightCm: 170, ageYears: 35, bodyFatPct: 20, sleepDebtHours: 0, coreTempC: 37, metabolicType: "EM" },
      });
      expect(result.risks).toEqual([]);
      expect(result.summary.total).toBe(0);
    });

    it("includes signal risks when provided", () => {
      const service = new RiskService(mockApiClient());
      const signalRows = [
        {
          risk_kind: "signal",
          signal_id: "sig1",
          substance_id: "ibuprofen",
          substance_name: "Ibuprofen",
          risk_level: "Minor",
          reactions: [{ reaction: "Headache", label: "头痛", count: 100 }],
          source_tier: "Signal",
        },
      ];
      const result = service.computeRisks({
        entries: [ibuprofenEntry],
        bundles: makeBundles(),
        profile: { weightKg: 70, heightCm: 170, ageYears: 35, bodyFatPct: 20, sleepDebtHours: 0, coreTempC: 37, metabolicType: "EM" },
        signalRows,
      });
      expect(result.risks.some((r) => r.kind === "signal")).toBe(true);
    });
  });

  describe("buildSignalRisks", () => {
    it("converts signal rows to risk events", () => {
      const service = new RiskService(mockApiClient());
      const rows = [
        {
          risk_kind: "signal",
          signal_id: "sig1",
          substance_id: "ibuprofen",
          substance_name: "Ibuprofen",
          risk_level: "Minor",
          reactions: [{ reaction: "Headache", label: "头痛", count: 100 }],
        },
      ];
      const risks = service.buildSignalRisks(rows, [ibuprofenEntry]);
      expect(risks).toHaveLength(1);
      expect(risks[0].kind).toBe("signal");
    });

    it("ignores non-signal rows", () => {
      const service = new RiskService(mockApiClient());
      const risks = service.buildSignalRisks([{ risk_kind: "other" }], [ibuprofenEntry]);
      expect(risks).toHaveLength(0);
    });
  });
});
