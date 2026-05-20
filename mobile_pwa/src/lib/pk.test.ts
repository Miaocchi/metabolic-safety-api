import { describe, expect, it } from "vitest";
import { adjustedPkParams, buildCurveModel, calculateFullPMI, defaultProfile, observedBaselineHalfLifeHours } from "./pk";
import type { JournalEntry, SubstanceBundle } from "../types";

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
});
