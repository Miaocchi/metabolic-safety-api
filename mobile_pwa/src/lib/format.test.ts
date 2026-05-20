import { describe, expect, it } from "vitest";
import { riskLabel, scoreItem, searchShardKey, searchShardKeysForQuery } from "./format";
import type { SubstanceSummary } from "../types";

describe("format/search helpers", () => {
  it("uses ASCII prefixes for shard keys", () => {
    expect(searchShardKey("Warfarin")).toBe("wa");
    expect(searchShardKey(" ibuprofen ")).toBe("ib");
  });

  it("uses unicode codepoint keys for Chinese queries", () => {
    expect(searchShardKey("布洛芬")).toMatch(/^u/);
    expect(searchShardKeysForQuery("布洛芬").length).toBeGreaterThan(0);
  });

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

  it("localizes unknown risk without treating it as safe", () => {
    expect(riskLabel("Unknown")).toBe("未知");
  });
});
