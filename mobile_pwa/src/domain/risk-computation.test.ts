import { describe, expect, it } from "vitest";
import type { JournalEntry, SubstanceBundle } from "../types";
import {
  adverseSignalRisks,
  doseRuleRisks,
  localStaticPairRisks,
  localInteractionRisks,
  overdoseEvidenceRisks,
  modelRisks,
  sortRisks,
} from "./risk-computation";
import { defaultProfile } from "./pk";

const now = Date.now();
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
  ...ibuprofenEntry,
  id: "e2",
  substanceId: "warfarin",
  substanceName: "Warfarin",
};

function makeBundles(overrides: Record<string, Partial<SubstanceBundle>> = {}): Record<string, SubstanceBundle> {
  const base: SubstanceBundle = {
    detail: { id: "ibuprofen", name_en: "Ibuprofen" },
    interactions: [],
    doseRules: [],
    doseCandidates: [],
    overdoseWarnings: [],
    drugEffects: [],
    pharmacokinetics: [],
    enzymeRelations: [],
    labelSections: [],
    safetyWarnings: [],
    interactionSignals: [],
    foodInteractions: [],
    adverseSignals: [],
    pgx: [],
    fetchedAt: now,
  };
  const result: Record<string, SubstanceBundle> = { ibuprofen: base };
  for (const [key, value] of Object.entries(overrides)) {
    result[key] = { ...base, ...value } as SubstanceBundle;
  }
  return result;
}

describe("domain/risk-computation", () => {
  describe("doseRuleRisks", () => {
    it("generates dose rule risks from indexed journal entries", () => {
      const bundles = makeBundles({
        ibuprofen: {
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
        },
      });
      const risks = doseRuleRisks([ibuprofenEntry], bundles);
      expect(risks).toHaveLength(1);
      expect(risks[0].level).toBe("Moderate");
    });

    it("returns empty when no dose rules match", () => {
      const bundles = makeBundles();
      expect(doseRuleRisks([ibuprofenEntry], bundles)).toEqual([]);
    });
  });

  describe("localStaticPairRisks", () => {
    it("falls back to cached static pair interactions", () => {
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
      const risks = localStaticPairRisks([ibuprofenEntry, warfarinEntry], bundles);
      expect(risks[0].title).toContain("Ibuprofen");
      expect(sortRisks(risks)[0].level).toBe("Major");
    });
  });

  describe("localInteractionRisks", () => {
    it("converts interaction rows to risk events", () => {
      const risks = localInteractionRisks(
        [{ interaction_id: "i1", substance_a_id: "ibu", substance_b_id: "war", risk_level: "Major" }],
        [ibuprofenEntry],
      );
      expect(risks).toHaveLength(1);
      expect(risks[0].kind).toBe("interaction");
    });
  });

  describe("overdoseEvidenceRisks", () => {
    it("creates risks for entries with overdose warnings", () => {
      const bundles = makeBundles({
        ibuprofen: {
          overdoseWarnings: [{ fact_id: "ow1", text: "Overdose risk", source_name: "DailyMed" }],
        },
      });
      const risks = overdoseEvidenceRisks([ibuprofenEntry], bundles);
      expect(risks).toHaveLength(1);
      expect(risks[0].kind).toBe("overdose");
    });

    it("returns empty when no overdose warnings", () => {
      const bundles = makeBundles();
      expect(overdoseEvidenceRisks([ibuprofenEntry], bundles)).toEqual([]);
    });
  });

  describe("modelRisks", () => {
    it("generates model risks for high-dose entries", () => {
      const highDoseEntry: JournalEntry = { ...ibuprofenEntry, dosage: 5000 };
      const risks = modelRisks([highDoseEntry], makeBundles(), defaultProfile);
      expect(risks.length).toBeGreaterThan(0);
      expect(risks[0].kind).toBe("model");
    });

    it("returns empty for low-dose normal-profile entries", () => {
      const lowDose: JournalEntry = { ...ibuprofenEntry, dosage: 200 };
      expect(modelRisks([lowDose], makeBundles(), defaultProfile)).toEqual([]);
    });
  });

  describe("adverseSignalRisks", () => {
    it("keeps low-count adverse event signals as minor", () => {
      const risks = adverseSignalRisks([
        {
          risk_kind: "signal",
          signal_id: "donepezil",
          substance_id: "donepezil",
          substance_name: "多奈哌齐",
          risk_level: "Moderate",
          reactions: [{ reaction: "ECG QT prolonged", label: "常见共报告事件", count: 6 }],
        },
      ], [{ ...ibuprofenEntry, substanceId: "donepezil", substanceName: "多奈哌齐" }]);

      expect(risks[0].level).toBe("Minor");
    });

    it("ignores non-signal rows", () => {
      const risks = adverseSignalRisks([{ risk_kind: "other" }], [ibuprofenEntry]);
      expect(risks).toHaveLength(0);
    });
  });

  describe("sortRisks", () => {
    it("sorts by severity descending", () => {
      const risks = sortRisks([
        { id: "a", level: "Minor", title: "B" },
        { id: "b", level: "Major", title: "A" },
      ]);
      expect(risks[0].level).toBe("Major");
    });
  });
});
