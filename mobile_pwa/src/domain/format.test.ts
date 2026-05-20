import { describe, expect, it } from "vitest";
import {
  riskLabels,
  riskRank,
  normalizeText,
  compactText,
  displayName,
  subName,
  scoreItem,
  searchShardKey,
  searchShardKeysForQuery,
  formatNumber,
  formatHours,
  riskClass,
  riskLabel,
  riskSortValue,
  routeLabel,
  stomachLabel,
  clippedText,
  haystack,
  aliasesOf,
  toDateTimeLocal,
  dateTimeLocalToTimestamp,
  formatJournalEntry,
} from "./format";
import type { SubstanceSummary, JournalEntry } from "../types";

describe("domain/format", () => {
  describe("riskLabels / riskRank", () => {
    it("contains all expected risk levels", () => {
      expect(riskLabels.Contraindicated).toBe("禁忌");
      expect(riskLabels.Unknown).toBe("未知");
      expect(riskLabels.NoKnownClinicalSignificance).toBe("无明确临床意义");
    });

    it("ranks Contraindicated highest", () => {
      expect(riskRank.Contraindicated).toBeGreaterThan(riskRank.Major);
    });
  });

  describe("normalizeText / compactText", () => {
    it("lowercases and normalizes whitespace", () => {
      expect(normalizeText("  Hello  World  ")).toBe("hello world");
    });

    it("removes all whitespace in compactText", () => {
      expect(compactText("hello world")).toBe("helloworld");
    });
  });

  describe("displayName / subName", () => {
    it("prefers Chinese name", () => {
      expect(displayName({ name_zh: "华法林", name_en: "Warfarin" })).toBe("华法林");
    });

    it("falls back to English name", () => {
      expect(displayName({ name_en: "Warfarin" })).toBe("Warfarin");
    });

    it("subName returns English when both names differ", () => {
      expect(subName({ name_zh: "华法林", name_en: "Warfarin" })).toBe("Warfarin");
    });
  });

  describe("searchShardKey / searchShardKeysForQuery", () => {
    it("uses ASCII prefixes for shard keys", () => {
      expect(searchShardKey("Warfarin")).toBe("wa");
      expect(searchShardKey(" ibuprofen ")).toBe("ib");
    });

    it("uses unicode codepoint keys for Chinese queries", () => {
      expect(searchShardKey("布洛芬")).toMatch(/^u/);
      expect(searchShardKeysForQuery("布洛芬").length).toBeGreaterThan(0);
    });
  });

  describe("scoreItem", () => {
    it("scores exact and alias matches above partial hits", () => {
      const item: SubstanceSummary = {
        id: "warfarin",
        name_en: "Warfarin",
        name_zh: "华法林",
        aliases: ["Coumadin"],
      };
      expect(scoreItem(item, "warfarin")).toBeGreaterThan(scoreItem(item, "warf"));
      expect(scoreItem(item, "Coumadin")).toBeGreaterThan(0);
    });
  });

  describe("riskLabel / riskClass / riskSortValue", () => {
    it("localizes unknown risk without treating it as safe", () => {
      expect(riskLabel("Unknown")).toBe("未知");
    });

    it("returns CSS-safe class name", () => {
      expect(riskClass("Low Risk")).toBe("low-risk");
    });

    it("sorts Unknown above NoKnownClinicalSignificance", () => {
      expect(riskSortValue("Unknown")).toBeGreaterThan(riskSortValue("NoKnownClinicalSignificance"));
    });
  });

  describe("formatNumber / formatHours", () => {
    it("formats numbers with zh-CN locale", () => {
      expect(formatNumber(1234)).toContain("1");
    });

    it("formats hours with 2 decimal places", () => {
      expect(formatHours(3.5)).toBe("3.50 h");
    });

    it("returns '未知' for null/undefined hours", () => {
      expect(formatHours(null)).toBe("未知");
      expect(formatHours(undefined)).toBe("未知");
    });
  });

  describe("routeLabel / stomachLabel", () => {
    it("returns Chinese labels for known routes", () => {
      expect(routeLabel("Oral")).toBe("口服");
      expect(routeLabel("IV")).toBe("静脉/瞬时");
    });

    it("returns Chinese labels for stomach states", () => {
      expect(stomachLabel("Fasting")).toBe("完全空腹");
      expect(stomachLabel("Heavy")).toBe("高脂重餐");
    });
  });

  describe("clippedText", () => {
    it("returns full text when under max", () => {
      expect(clippedText("short", 100)).toBe("short");
    });

    it("clips with ellipsis when over max", () => {
      const result = clippedText("a".repeat(300), 240);
      // clippedText keeps max-1 chars + "..." = max+2 chars
      expect(result.length).toBeLessThanOrEqual(243);
      expect(result).toContain("...");
    });
  });

  describe("toDateTimeLocal / dateTimeLocalToTimestamp", () => {
    it("round-trips a timestamp", () => {
      const ts = Date.now();
      const local = toDateTimeLocal(ts);
      const back = dateTimeLocalToTimestamp(local);
      // Allow timezone rounding tolerance
      expect(Math.abs(back - ts)).toBeLessThan(120000);
    });
  });

  describe("formatJournalEntry", () => {
    it("formats entry with dosage, route, and stomach state", () => {
      const entry: JournalEntry = {
        id: "1",
        substanceId: "ibu",
        substanceName: "Ibuprofen",
        timestamp: Date.now(),
        dosage: 200,
        unit: "mg",
        route: "Oral",
        stomachState: "Light",
      };
      expect(formatJournalEntry(entry)).toContain("200");
      expect(formatJournalEntry(entry)).toContain("口服");
    });
  });

  describe("haystack / aliasesOf", () => {
    it("builds a search haystack from item fields", () => {
      const item: SubstanceSummary = { id: "ibu", name_en: "Ibuprofen", name_zh: "布洛芬", aliases: ["Advil"] };
      const h = haystack(item);
      expect(h).toContain("ibu");
      expect(h).toContain("ibuprofen");
      expect(h).toContain("布洛芬");
    });

    it("returns aliases array", () => {
      expect(aliasesOf({ aliases: ["A", "B"] })).toEqual(["A", "B"]);
      expect(aliasesOf(undefined)).toEqual([]);
    });
  });
});
