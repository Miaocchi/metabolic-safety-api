import { describe, expect, it } from "vitest";
import type { JournalEntry, SubstanceBundle } from "../types";
import { adverseSignalRisks, doseRuleRisks, localStaticPairRisks, sortRisks } from "./risks";

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

describe("risk aggregation", () => {
  it("generates dose rule risks from indexed journal entries", () => {
    const bundles: Record<string, SubstanceBundle> = {
      ibuprofen: {
        detail: { id: "ibuprofen", name_en: "Ibuprofen" },
        interactions: [],
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
    };
    const risks = doseRuleRisks([ibuprofenEntry], bundles);
    expect(risks).toHaveLength(1);
    expect(risks[0].level).toBe("Moderate");
  });

  it("falls back to cached static pair interactions", () => {
    const warfarinEntry: JournalEntry = {
      ...ibuprofenEntry,
      id: "e2",
      substanceId: "warfarin",
      substanceName: "Warfarin",
    };
    const bundles: Record<string, SubstanceBundle> = {
      ibuprofen: {
        detail: { id: "ibuprofen", name_en: "Ibuprofen" },
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
    };
    const risks = localStaticPairRisks([ibuprofenEntry, warfarinEntry], bundles);
    expect(risks[0].title).toContain("Ibuprofen");
    expect(sortRisks(risks)[0].level).toBe("Major");
  });

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
});
