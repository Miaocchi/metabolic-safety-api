import { describe, expect, it } from "vitest";
import type { InteractionRow, RiskEvent } from "../types";
import {
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

describe("domain/risk", () => {
  describe("validateRiskEventDraft", () => {
    it("passes for a valid draft", () => {
      const draft: RiskEventDraft = {
        id: "test-1",
        kind: "interaction",
        level: "Major",
        title: "Test Risk",
      };
      expect(validateRiskEventDraft(draft)).toEqual([]);
    });

    it("fails when id is missing", () => {
      const errors = validateRiskEventDraft({ id: "", kind: "interaction", level: "Major", title: "Test" });
      expect(errors.length).toBeGreaterThan(0);
      expect(errors[0]).toContain("id");
    });

    it("fails when title is missing", () => {
      const errors = validateRiskEventDraft({ id: "x", kind: "interaction", level: "Major", title: "" });
      expect(errors.length).toBeGreaterThan(0);
    });
  });

  describe("shouldApplyCandidateRisk", () => {
    it("always applies non-candidate risks", () => {
      expect(shouldApplyCandidateRisk("Regulatory", "Community")).toBe(true);
      expect(shouldApplyCandidateRisk("Reviewed", undefined)).toBe(true);
    });

    it("applies candidate risks when no existing risk", () => {
      expect(shouldApplyCandidateRisk("Signal", undefined)).toBe(true);
      expect(shouldApplyCandidateRisk("Community", undefined)).toBe(true);
    });

    it("applies candidate risks when existing is also candidate", () => {
      expect(shouldApplyCandidateRisk("Signal", "Community")).toBe(true);
      expect(shouldApplyCandidateRisk("Community", "Signal")).toBe(true);
    });

    it("blocks candidate risks from overriding higher-tier risks", () => {
      expect(shouldApplyCandidateRisk("Signal", "Regulatory")).toBe(false);
      expect(shouldApplyCandidateRisk("Community", "Reviewed")).toBe(false);
      expect(shouldApplyCandidateRisk("Signal", "Curated")).toBe(false);
    });
  });

  describe("mergeRiskEvents", () => {
    it("prefers higher tier authority", () => {
      const regulatory: RiskEvent = {
        id: "r1",
        level: "Moderate",
        title: "Regulatory",
        sourceTier: "Regulatory",
      };
      const signal: RiskEvent = {
        id: "r1",
        level: "Major",
        title: "Signal",
        sourceTier: "Signal",
      };
      const merged = mergeRiskEvents(regulatory, signal);
      expect(merged.sourceTier).toBe("Regulatory");
    });

    it("prefers higher severity when tiers are equal", () => {
      const minor: RiskEvent = {
        id: "r1",
        level: "Minor",
        title: "Minor",
        sourceTier: "Reviewed",
      };
      const major: RiskEvent = {
        id: "r1",
        level: "Major",
        title: "Major",
        sourceTier: "Reviewed",
      };
      const merged = mergeRiskEvents(minor, major);
      expect(merged.level).toBe("Major");
    });
  });

  describe("deduplicateRisks", () => {
    it("remuplicates by id", () => {
      const risks: RiskEvent[] = [
        { id: "a", level: "Minor", title: "First" },
        { id: "a", level: "Major", title: "Second" },
        { id: "b", level: "Moderate", title: "Third" },
      ];
      const deduped = deduplicateRisks(risks);
      expect(deduped).toHaveLength(2);
    });

    it("keeps the highest-authority version", () => {
      const risks: RiskEvent[] = [
        { id: "a", level: "Major", title: "Signal", sourceTier: "Signal" },
        { id: "a", level: "Minor", title: "Regulatory", sourceTier: "Regulatory" },
      ];
      const deduped = deduplicateRisks(risks);
      expect(deduped[0].sourceTier).toBe("Regulatory");
    });
  });

  describe("sortRisksBySeverity", () => {
    it("sorts by severity descending", () => {
      const risks: RiskEvent[] = [
        { id: "a", level: "Minor", title: "B" },
        { id: "b", level: "Major", title: "A" },
        { id: "c", level: "Moderate", title: "C" },
      ];
      const sorted = sortRisksBySeverity(risks);
      expect(sorted[0].level).toBe("Major");
      expect(sorted[1].level).toBe("Moderate");
      expect(sorted[2].level).toBe("Minor");
    });

    it("sorts by title when severity is equal", () => {
      const risks: RiskEvent[] = [
        { id: "a", level: "Major", title: "布洛芬" },
        { id: "b", level: "Major", title: "阿司匹林" },
      ];
      const sorted = sortRisksBySeverity(risks);
      expect(sorted[0].title.localeCompare(sorted[1].title, "zh-CN")).toBeLessThanOrEqual(0);
    });

    it("treats Unknown as severity 1 (not 0)", () => {
      const risks: RiskEvent[] = [
        { id: "a", level: "Unknown", title: "Unknown" },
        { id: "b", level: "NoKnownClinicalSignificance", title: "Safe" },
      ];
      const sorted = sortRisksBySeverity(risks);
      expect(sorted[0].level).toBe("Unknown");
      expect(sorted[1].level).toBe("NoKnownClinicalSignificance");
    });
  });

  describe("filterHighRisks", () => {
    it("filters by default Major threshold", () => {
      const risks: RiskEvent[] = [
        { id: "a", level: "Major", title: "Major" },
        { id: "b", level: "Minor", title: "Minor" },
        { id: "c", level: "Contraindicated", title: "Contra" },
      ];
      expect(filterHighRisks(risks)).toHaveLength(2);
    });

    it("can filter by custom threshold", () => {
      const risks: RiskEvent[] = [
        { id: "a", level: "Major", title: "Major" },
        { id: "b", level: "Minor", title: "Minor" },
        { id: "c", level: "Moderate", title: "Moderate" },
      ];
      expect(filterHighRisks(risks, "Moderate")).toHaveLength(2);
    });

    it("excludes Unknown from high risks", () => {
      const risks: RiskEvent[] = [
        { id: "a", level: "Unknown", title: "Unknown" },
      ];
      expect(filterHighRisks(risks)).toHaveLength(0);
    });
  });

  describe("riskSummary", () => {
    it("counts categories correctly", () => {
      const risks: RiskEvent[] = [
        { id: "a", level: "Major", title: "Critical" },
        { id: "b", level: "Moderate", title: "Warning" },
        { id: "c", level: "Unknown", title: "Unknown" },
        { id: "d", level: "Minor", title: "Info" },
      ];
      const summary = riskSummary(risks);
      expect(summary.total).toBe(4);
      expect(summary.critical).toBe(1);
      expect(summary.warning).toBe(1);
      expect(summary.unknown).toBe(1);
      expect(summary.highRiskCount).toBe(1);
    });

    it("handles empty input", () => {
      const summary = riskSummary([]);
      expect(summary.total).toBe(0);
      expect(summary.critical).toBe(0);
    });
  });

  describe("interaction helpers", () => {
    const row: InteractionRow = {
      interaction_id: "i1",
      substance_a_id: "ibuprofen",
      substance_b_id: "warfarin",
      substance_a_name: "布洛芬",
      substance_b_name: "华法林",
      risk_level: "Major",
      action: "出血风险增加",
      conflict_status: "conflict",
    };

    it("builds title from substance names", () => {
      expect(interactionTitle(row)).toBe("布洛芬 / 华法林");
    });

    it("falls back to English names", () => {
      const fallback: InteractionRow = { ...row, substance_a_name: undefined, substance_b_name: undefined, substance_a_name_en: "Ibuprofen", substance_b_name_en: "Warfarin" };
      expect(interactionTitle(fallback)).toBe("Ibuprofen / Warfarin");
    });

    it("builds subtitle from action", () => {
      expect(interactionSubtitle(row)).toBe("出血风险增加");
    });

    it("falls back to interaction_type for subtitle", () => {
      const fallback: InteractionRow = { ...row, action: undefined, interaction_type: "pharmacodynamic" };
      expect(interactionSubtitle(fallback)).toBe("pharmacodynamic");
    });

    it("returns effective level preserving Unknown", () => {
      expect(interactionEffectiveLevel(row)).toBe("Major");
      expect(interactionEffectiveLevel({ ...row, risk_level: undefined })).toBe("Unknown");
      expect(interactionEffectiveLevel({ ...row, risk_level: "Unknown" })).toBe("Unknown");
    });

    it("returns interaction kind based on conflict_status", () => {
      expect(interactionKind(row)).toBe("conflict");
      expect(interactionKind({ ...row, conflict_status: undefined })).toBe("interaction");
    });
  });
});
