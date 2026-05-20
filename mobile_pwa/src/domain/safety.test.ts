import { describe, expect, it } from "vitest";
import {
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
  SOURCE_TIERS,
  RISK_SEVERITY,
  SAFETY_NOTES,
} from "./safety";

describe("domain/safety", () => {
  describe("source tier hierarchy", () => {
    it("ranks Regulatory as highest authority", () => {
      expect(sourceTierRank("Regulatory")).toBeGreaterThan(sourceTierRank("Community"));
      expect(sourceTierRank("Regulatory")).toBeGreaterThan(sourceTierRank("Signal"));
    });

    it("ranks Community and Signal as lowest authority", () => {
      expect(sourceTierRank("Community")).toBeLessThan(sourceTierRank("Reviewed"));
      expect(sourceTierRank("Signal")).toBeLessThan(sourceTierRank("Reviewed"));
    });

    it("returns 0 for unknown tiers", () => {
      expect(sourceTierRank("BogusTier")).toBe(0);
      expect(sourceTierRank(undefined)).toBe(0);
    });

    it("identifies candidate/weak tiers", () => {
      expect(isCandidateTier("Signal")).toBe(true);
      expect(isCandidateTier("Community")).toBe(true);
      expect(isCandidateTier("Regulatory")).toBe(false);
      expect(isCandidateTier("Reviewed")).toBe(false);
      expect(isCandidateTier(undefined)).toBe(false);
    });

    it("checks tier minimums", () => {
      expect(tierMeetsMinimum("Regulatory", "Reviewed")).toBe(true);
      expect(tierMeetsMinimum("Reviewed", "Reviewed")).toBe(true);
      expect(tierMeetsMinimum("Community", "Reviewed")).toBe(false);
      expect(tierMeetsMinimum(undefined, "Reviewed")).toBe(false);
    });

    it("defines all expected tiers", () => {
      expect(SOURCE_TIERS).toContain("Regulatory");
      expect(SOURCE_TIERS).toContain("Signal");
      expect(SOURCE_TIERS).toContain("Community");
      expect(SOURCE_TIERS).toContain("LocalModel");
    });
  });

  describe("risk severity classification", () => {
    it("CRITICAL: Unknown=1, not 0 — Unknown ≠ Safe", () => {
      expect(riskSeverity("Unknown")).toBe(1);
      expect(RISK_SEVERITY.Unknown).toBe(1);
      // This is the most important invariant
    });

    it("NoKnownClinicalSignificance is the only safe level", () => {
      expect(riskSeverity("NoKnownClinicalSignificance")).toBe(0);
      expect(RISK_SEVERITY.NoKnownClinicalSignificance).toBe(0);
    });

    it("Unknown has higher severity than NoKnownClinicalSignificance", () => {
      expect(riskSeverity("Unknown")).toBeGreaterThan(riskSeverity("NoKnownClinicalSignificance"));
    });

    it("ranks Contraindicated as highest severity", () => {
      expect(riskSeverity("Contraindicated")).toBe(7);
      for (const level of Object.keys(RISK_SEVERITY)) {
        if (level !== "Contraindicated") {
          expect(riskSeverity("Contraindicated")).toBeGreaterThanOrEqual(riskSeverity(level));
        }
      }
    });

    it("Dangerous and Unsafe share same high severity", () => {
      expect(riskSeverity("Dangerous")).toBe(riskSeverity("Unsafe"));
      expect(riskSeverity("Dangerous")).toBe(6);
    });

    it("returns 1 for completely unknown/empty levels", () => {
      expect(riskSeverity(undefined)).toBe(1);
      expect(riskSeverity("")).toBe(1);
      expect(riskSeverity("BogusLevel")).toBe(1);
    });
  });

  describe("safety classification helpers", () => {
    it("isKnownSafe only matches NoKnownClinicalSignificance", () => {
      expect(isKnownSafe("NoKnownClinicalSignificance")).toBe(true);
      expect(isKnownSafe("Unknown")).toBe(false);
      expect(isKnownSafe("Minor")).toBe(false);
      expect(isKnownSafe(undefined)).toBe(false);
    });

    it("isUnknownRisk matches Unknown and empty/undefined", () => {
      expect(isUnknownRisk("Unknown")).toBe(true);
      expect(isUnknownRisk(undefined)).toBe(true);
      expect(isUnknownRisk("")).toBe(true);
      expect(isUnknownRisk("NoKnownClinicalSignificance")).toBe(false);
      expect(isUnknownRisk("Minor")).toBe(false);
    });

    it("isClinicallySignificant excludes Unknown and safe", () => {
      expect(isClinicallySignificant("Major")).toBe(true);
      expect(isClinicallySignificant("Moderate")).toBe(true);
      expect(isClinicallySignificant("Unknown")).toBe(false);
      expect(isClinicallySignificant("NoKnownClinicalSignificance")).toBe(false);
    });

    it("isHighSeverity includes Major and above", () => {
      expect(isHighSeverity("Contraindicated")).toBe(true);
      expect(isHighSeverity("Dangerous")).toBe(true);
      expect(isHighSeverity("Major")).toBe(true);
      expect(isHighSeverity("Moderate")).toBe(false);
      expect(isHighSeverity("Minor")).toBe(false);
      expect(isHighSeverity("Unknown")).toBe(false);
    });
  });

  describe("categorizeRisk", () => {
    it("returns 'safe' only for NoKnownClinicalSignificance", () => {
      expect(categorizeRisk("NoKnownClinicalSignificance")).toBe("safe");
    });

    it("returns 'unknown' for Unknown", () => {
      expect(categorizeRisk("Unknown")).toBe("unknown");
      expect(categorizeRisk(undefined)).toBe("unknown");
    });

    it("returns 'critical' for Major and above", () => {
      expect(categorizeRisk("Contraindicated")).toBe("critical");
      expect(categorizeRisk("Major")).toBe("critical");
    });

    it("returns 'warning' for Moderate and Synergy", () => {
      expect(categorizeRisk("Moderate")).toBe("warning");
      expect(categorizeRisk("Synergy")).toBe("warning");
    });

    it("returns 'info' for Minor and Low Risk", () => {
      expect(categorizeRisk("Minor")).toBe("info");
      expect(categorizeRisk("Low Risk")).toBe("info");
    });
  });

  describe("interactionKindLabel", () => {
    it("returns Chinese labels for all known kinds", () => {
      expect(interactionKindLabel("conflict")).toBe("冲突");
      expect(interactionKindLabel("interaction")).toBe("相互作用");
      expect(interactionKindLabel("dose")).toBe("过量");
      expect(interactionKindLabel("overdose")).toBe("过量");
      expect(interactionKindLabel("signal")).toBe("警戒信号");
      expect(interactionKindLabel("model")).toBe("模型提示");
    });

    it("defaults to '相互作用' for unknown kinds", () => {
      expect(interactionKindLabel(undefined)).toBe("相互作用");
      expect(interactionKindLabel("bogus")).toBe("相互作用");
    });
  });

  describe("SAFETY_NOTES constants", () => {
    it("contains Unknown ≠ Safe note", () => {
      expect(SAFETY_NOTES.unknownNotSafe).toContain("Unknown");
      expect(SAFETY_NOTES.unknownNotSafe).toContain("不能显示为安全");
    });

    it("contains community candidate note", () => {
      expect(SAFETY_NOTES.communityCandidate).toContain("候选");
    });

    it("contains signal candidate note", () => {
      expect(SAFETY_NOTES.signalCandidate).toContain("不代表因果关系");
    });

    it("contains label text evidence note (not clinical instructions)", () => {
      expect(SAFETY_NOTES.labelTextEvidence).toContain("证据摘录");
      expect(SAFETY_NOTES.labelTextEvidence).toContain("不是临床用药指导");
    });

    it("contains safety warning extraction note (machine extraction caveat)", () => {
      expect(SAFETY_NOTES.safetyWarningExtraction).toContain("机器提取");
      expect(SAFETY_NOTES.safetyWarningExtraction).toContain("不能替代");
    });

    it("contains interaction signal review note (not DDInter replacement)", () => {
      expect(SAFETY_NOTES.interactionSignalReview).toContain("DDInter");
      expect(SAFETY_NOTES.interactionSignalReview).toContain("需人工复核");
    });

    it("contains food interaction candidate note (FooDrugs low confidence)", () => {
      expect(SAFETY_NOTES.foodInteractionCandidate).toContain("FooDrugs");
      expect(SAFETY_NOTES.foodInteractionCandidate).toContain("低置信度");
      expect(SAFETY_NOTES.foodInteractionCandidate).toContain("不代表因果关系");
    });

    it("contains adverse signal note (not incidence or causality)", () => {
      expect(SAFETY_NOTES.adverseSignalNotIncidence).toContain("OnSIDES");
      expect(SAFETY_NOTES.adverseSignalNotIncidence).toContain("不代表发生率或因果关系");
    });

    it("contains PGx evidence-only note (not individualized prescribing)", () => {
      expect(SAFETY_NOTES.pgxEvidenceOnly).toContain("PharmGKB");
      expect(SAFETY_NOTES.pgxEvidenceOnly).toContain("不是个体化处方建议");
      expect(SAFETY_NOTES.pgxEvidenceOnly).toContain("Unknown ≠ 安全");
    });
  });
});
