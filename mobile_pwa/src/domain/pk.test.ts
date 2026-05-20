import { describe, expect, it } from "vitest";
import {
  defaultProfile,
  doseInMg,
  adjustedPkParams,
  concentrationAt,
  baselineHalfLifeHours,
  observedBaselineHalfLifeHours,
  substanceDetailForModel,
  activeEntries,
  calculatePMI,
  pmiLabel,
  calculateFullPMI,
  buildCurveModel,
  exposureMetricsForEntry,
  forwardExposureIndex,
} from "./pk";
import type { JournalEntry, SubstanceBundle, UserProfile } from "../types";

const now = new Date("2026-05-20T12:00:00Z").getTime();

function entry(overrides: Partial<JournalEntry> = {}): JournalEntry {
  return {
    id: "entry-1",
    substanceId: "amlodipine",
    substanceName: "Amlodipine",
    timestamp: now - 60 * 60 * 1000,
    dosage: 10,
    unit: "mg",
    route: "Oral",
    stomachState: "Light",
    ...overrides,
  };
}

function bundle(pkRows: SubstanceBundle["pharmacokinetics"]): SubstanceBundle {
  return {
    detail: {
      id: "amlodipine",
      name_en: "Amlodipine",
      paths: { pharmacokinetics: "pharmacokinetics/by-substance/am/amlodipine.json" },
    },
    interactions: [],
    doseRules: [],
    doseCandidates: [],
    overdoseWarnings: [],
    drugEffects: [],
    pharmacokinetics: pkRows,
    enzymeRelations: [],
    labelSections: [],
    safetyWarnings: [],
    interactionSignals: [],
    foodInteractions: [],
    adverseSignals: [],
    pgx: [],
    fetchedAt: now,
  };
}

describe("domain/pk", () => {
  describe("defaultProfile", () => {
    it("has expected defaults", () => {
      expect(defaultProfile.weightKg).toBe(70);
      expect(defaultProfile.metabolicType).toBe("EM");
    });
  });

  describe("doseInMg", () => {
    it("converts mg directly", () => {
      expect(doseInMg(entry({ dosage: 200, unit: "mg" }))).toBe(200);
    });

    it("converts g to mg", () => {
      expect(doseInMg(entry({ dosage: 1, unit: "g" }))).toBe(1000);
    });

    it("converts mcg to mg", () => {
      expect(doseInMg(entry({ dosage: 500, unit: "mcg" }))).toBe(0.5);
    });

    it("returns 0 for invalid dose", () => {
      expect(doseInMg(entry({ dosage: -1 }))).toBe(0);
      expect(doseInMg(entry({ dosage: 0 }))).toBe(0);
    });
  });

  describe("adjustedPkParams", () => {
    it("returns one-compartment model for oral route", () => {
      const params = adjustedPkParams(entry(), undefined, defaultProfile);
      expect(params.modelType).toBe("one_compartment_absorption");
      expect(params.kePerHour).toBeGreaterThan(0);
      expect(params.kaPerHour).toBeGreaterThan(0);
    });

    it("returns instant elimination for IV route", () => {
      const params = adjustedPkParams(entry({ route: "IV" }), undefined, defaultProfile);
      expect(params.modelType).toBe("instant_elimination");
      expect(params.kaPerHour).toBe(0);
    });
  });

  describe("concentrationAt", () => {
    it("returns 0 at negative time", () => {
      const params = adjustedPkParams(entry(), undefined, defaultProfile);
      expect(concentrationAt(-1, 10, params)).toBe(0);
    });

    it("returns 0 at t=0 for absorption model (drug not yet absorbed)", () => {
      const params = adjustedPkParams(entry(), undefined, defaultProfile);
      // One-compartment absorption: C(0) = 0 because exp(-ke*0) - exp(-ka*0) = 0
      expect(concentrationAt(0, 10, params)).toBe(0);
    });

    it("reaches peak then decreases over time", () => {
      const params = adjustedPkParams(entry(), undefined, defaultProfile);
      const c1 = concentrationAt(1, 10, params);
      const c4 = concentrationAt(4, 10, params);
      const c24 = concentrationAt(24, 10, params);
      // After absorption, concentration rises then falls
      expect(c1).toBeGreaterThan(0);
      expect(c24).toBeLessThan(c4);
    });
  });

  describe("PK baseline half-life", () => {
    it("uses pharmacokinetic overlay rows when detail base_half_life is absent", () => {
      const substanceBundle = bundle([
        {
          fact_id: "pk-amlodipine",
          source_name: "DailyMed SPL bulk",
          source_tier: "Regulatory",
          half_life_hours: 56,
        },
      ]);
      const entries = [entry()];
      const bundles = { amlodipine: substanceBundle };

      const model = buildCurveModel(entries, bundles, defaultProfile, 1, 0, now);
      const pmi = calculateFullPMI(entries, bundles, defaultProfile, [], now);

      expect(observedBaselineHalfLifeHours({ ...substanceBundle.detail, pharmacokinetics: substanceBundle.pharmacokinetics })).toBe(56);
      expect(model.series[0].baseHalfLifeHours).toBe(56);
      expect(model.series[0].adjustedHalfLifeHours).toBeCloseTo(56, 6);
      expect(pmi.rows[0].halfLife).toBeCloseTo(56, 6);
    });

    it("prefers fused base_half_life over overlay rows", () => {
      const params = adjustedPkParams(entry(), {
        id: "amlodipine",
        base_half_life: 30,
        pharmacokinetics: [{ half_life_hours: 56 }],
      });

      expect(params.baseHalfLifeHours).toBe(30);
    });

    it("returns default when no data available", () => {
      expect(baselineHalfLifeHours(undefined)).toBe(4);
      expect(baselineHalfLifeHours(null)).toBe(4);
    });
  });

  describe("activeEntries", () => {
    it("includes recent entries within the activity window", () => {
      const entries = [entry({ timestamp: now - 30 * 60000 })];
      const bundles = { amlodipine: bundle([]) };
      expect(activeEntries(entries, bundles, defaultProfile, now).length).toBe(1);
    });

    it("excludes very old entries", () => {
      const entries = [entry({ timestamp: now - 72 * 3600000 })];
      const bundles = { amlodipine: bundle([]) };
      expect(activeEntries(entries, bundles, defaultProfile, now).length).toBe(0);
    });
  });

  describe("calculatePMI", () => {
    it("returns value in expected range for default profile", () => {
      const result = calculatePMI(defaultProfile);
      expect(result.value).toBeGreaterThanOrEqual(20);
      expect(result.value).toBeLessThanOrEqual(180);
    });
  });

  describe("pmiLabel", () => {
    it("returns label and color for each range", () => {
      expect(pmiLabel(150).label).toBe("极快代谢");
      expect(pmiLabel(95).label).toBe("正常代谢");
      expect(pmiLabel(40).label).toBe("极慢代谢");
    });
  });

  describe("exposureMetricsForEntry", () => {
    it("computes auc24, cmax, and tmax", () => {
      const params = adjustedPkParams(entry(), undefined, defaultProfile);
      const metrics = exposureMetricsForEntry(entry(), params);
      expect(metrics.auc24).toBeGreaterThan(0);
      expect(metrics.cmax).toBeGreaterThan(0);
      expect(metrics.tmaxHours).toBeGreaterThanOrEqual(0);
    });
  });

  describe("forwardExposureIndex", () => {
    it("returns 0..100 range", () => {
      const idx = forwardExposureIndex(100, 50, 60, 8);
      expect(idx).toBeGreaterThanOrEqual(0);
      expect(idx).toBeLessThanOrEqual(100);
    });

    it("returns 0 for zero values", () => {
      expect(forwardExposureIndex(0, 0, 0, 0)).toBe(0);
    });
  });

  describe("substanceDetailForModel", () => {
    it("returns undefined for undefined bundle", () => {
      expect(substanceDetailForModel(undefined)).toBeUndefined();
    });

    it("returns detail when no PK rows", () => {
      const b = bundle([]);
      expect(substanceDetailForModel(b)?.id).toBe("amlodipine");
    });
  });
});
