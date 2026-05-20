import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClient } from "./api";

describe("ApiClient", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads search manifest and query shards", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/api/search/manifest.json")) {
        return jsonResponse({ shard_path: "search/shards/{key}.json", shards: { wa: 1 } });
      }
      if (url.endsWith("/api/search/shards/wa.json")) {
        return jsonResponse([{ id: "warfarin", name_en: "Warfarin", name_zh: "华法林", aliases: [] }]);
      }
      return jsonResponse({}, 404);
    });

    const rows = await new ApiClient("/api", "/local-api").search("warfarin");

    expect(rows).toHaveLength(1);
    expect(rows[0].id).toBe("warfarin");
    expect(fetchMock).toHaveBeenCalledWith("/api/search/shards/wa.json", expect.any(Object));
  });

  it("returns empty rows when a shard is absent from the manifest", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/api/search/manifest.json")) {
        return jsonResponse({ shard_path: "search/shards/{key}.json", shards: { wa: 1 } });
      }
      return jsonResponse({}, 404);
    });

    await expect(new ApiClient("/api", "/local-api").search("zzzz")).resolves.toEqual([]);
  });

  it("reads wrapped static adverse signal payloads", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/api/adverse_signals/warfarin.json")) {
        return jsonResponse({ items: [{ risk_kind: "signal", signal_id: "static_signal_warfarin", substance_id: "warfarin" }] });
      }
      return jsonResponse({}, 404);
    });

    const rows = await new ApiClient("/api", "/local-api").adverseSignals([{ id: "warfarin", name_en: "Warfarin" }]);

    expect(rows).toHaveLength(1);
    expect((rows[0] as { signal_id?: string }).signal_id).toBe("static_signal_warfarin");
  });

  it("merges pharmacokinetic overlay rows into substance details", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/api/substances/by-id/am/amlodipine.json")) {
        return jsonResponse({
          id: "amlodipine",
          name_en: "Amlodipine",
          paths: { pharmacokinetics: "pharmacokinetics/by-substance/am/amlodipine.json" },
        });
      }
      if (url.endsWith("/api/pharmacokinetics/by-substance/am/amlodipine.json")) {
        return jsonResponse([{ fact_id: "pk-1", half_life_hours: 56, onset_minutes: 120, duration_minutes: 1440 }]);
      }
      return jsonResponse([], 404);
    });

    const bundle = await new ApiClient("/api", "/local-api").fetchBundle({
      id: "amlodipine",
      name_en: "Amlodipine",
      paths: { substance: "substances/by-id/am/amlodipine.json" },
    });

    expect(bundle.detail.base_half_life).toBe(56);
    expect(bundle.detail.base_onset).toBe(120);
    expect(bundle.detail.base_duration).toBe(1440);
    expect(bundle.detail.remote_evidence?.pharmacokinetics?.[0].fact_id).toBe("pk-1");
  });

  it("fetches all 6 new content overlay endpoints from paths", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/api/substances/by-id/ab/acetaminophen.json")) {
        return jsonResponse({
          id: "acetaminophen",
          name_en: "Acetaminophen",
          label_section_count: 2,
          safety_warning_count: 1,
          interaction_signal_count: 1,
          food_interaction_count: 1,
          adverse_signal_count: 1,
          pgx_count: 1,
          paths: {
            substance: "substances/by-id/ab/acetaminophen.json",
            label_sections: "label-sections/by-substance/ab/acetaminophen.json",
            safety_warnings: "safety-warnings/by-substance/ab/acetaminophen.json",
            interaction_signals: "interaction-signals/by-substance/ab/acetaminophen.json",
            food_interactions: "food-interactions/by-substance/ab/acetaminophen.json",
            adverse_signals: "adverse-signals/by-substance/ab/acetaminophen.json",
            pgx: "pgx/by-substance/ab/acetaminophen.json",
          },
        });
      }
      if (url.includes("label-sections/")) {
        return jsonResponse([{ fact_id: "ls-1", section: "indications", text: "For pain relief" }]);
      }
      if (url.includes("safety-warnings/")) {
        return jsonResponse([{ fact_id: "sw-1", risk_level: "Major", section: "hepatotoxicity", warning_text: "Hepatotoxicity risk" }]);
      }
      if (url.includes("interaction-signals/")) {
        return jsonResponse([{ fact_id: "is-1", risk_level: "Moderate", section: "warfarin", interaction_text: "May increase INR" }]);
      }
      if (url.includes("food-interactions/")) {
        return jsonResponse([{ fact_id: "fi-1", drug: "Acetaminophen", food_or_bioactive: "Alcohol", mechanism: "CYP2E1 induction" }]);
      }
      if (url.includes("adverse-signals/")) {
        return jsonResponse([{ fact_id: "as-1", event: "Hepatotoxicity", risk_level: "Major" }]);
      }
      if (url.includes("pgx/")) {
        return jsonResponse([{ fact_id: "pgx-1", gene: "CYP2D6", section: "clinical_annotation", summary: "Poor metabolizers may have altered response" }]);
      }
      return jsonResponse([], 404);
    });

    const bundle = await new ApiClient("/api", "/local-api").fetchBundle({
      id: "acetaminophen",
      name_en: "Acetaminophen",
      paths: {
        substance: "substances/by-id/ab/acetaminophen.json",
        label_sections: "label-sections/by-substance/ab/acetaminophen.json",
        safety_warnings: "safety-warnings/by-substance/ab/acetaminophen.json",
        interaction_signals: "interaction-signals/by-substance/ab/acetaminophen.json",
        food_interactions: "food-interactions/by-substance/ab/acetaminophen.json",
        adverse_signals: "adverse-signals/by-substance/ab/acetaminophen.json",
        pgx: "pgx/by-substance/ab/acetaminophen.json",
      },
    });

    expect(bundle.labelSections).toHaveLength(1);
    expect(bundle.labelSections[0].fact_id).toBe("ls-1");
    expect(bundle.labelSections[0].text).toBe("For pain relief");

    expect(bundle.safetyWarnings).toHaveLength(1);
    expect(bundle.safetyWarnings[0].warning_text).toBe("Hepatotoxicity risk");
    expect(bundle.safetyWarnings[0].risk_level).toBe("Major");

    expect(bundle.interactionSignals).toHaveLength(1);
    expect(bundle.interactionSignals[0].interaction_text).toBe("May increase INR");

    expect(bundle.foodInteractions).toHaveLength(1);
    expect(bundle.foodInteractions[0].drug).toBe("Acetaminophen");
    expect(bundle.foodInteractions[0].food_or_bioactive).toBe("Alcohol");

    expect(bundle.adverseSignals).toHaveLength(1);
    expect(bundle.adverseSignals[0].event).toBe("Hepatotoxicity");

    expect(bundle.pgx).toHaveLength(1);
    expect(bundle.pgx[0].gene).toBe("CYP2D6");
    expect(bundle.pgx[0].summary).toContain("Poor metabolizers");

    // Detail counts from substance JSON should be preserved
    expect(bundle.detail.label_section_count).toBe(2);
    expect(bundle.detail.safety_warning_count).toBe(1);
    expect(bundle.detail.pgx_count).toBe(1);
  });

  it("gracefully returns empty arrays when overlay paths are absent", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/api/substances/by-id/xy/xyz.json")) {
        return jsonResponse({ id: "xyz", name_en: "XYZ" });
      }
      return jsonResponse([], 404);
    });

    const bundle = await new ApiClient("/api", "/local-api").fetchBundle({
      id: "xyz",
      name_en: "XYZ",
      paths: { substance: "substances/by-id/xy/xyz.json" },
    });

    expect(bundle.labelSections).toEqual([]);
    expect(bundle.safetyWarnings).toEqual([]);
    expect(bundle.interactionSignals).toEqual([]);
    expect(bundle.foodInteractions).toEqual([]);
    expect(bundle.adverseSignals).toEqual([]);
    expect(bundle.pgx).toEqual([]);
  });

  it("includes overlay paths from search index item", async () => {
    // Verify that paths from the search index SubstanceSummary
    // are passed through to overlay fetches
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/api/substances/by-id/wa/warfarin.json")) {
        return jsonResponse({ id: "warfarin", name_en: "Warfarin" });
      }
      if (url.includes("safety-warnings/")) {
        return jsonResponse([{ fact_id: "sw-warfarin", warning_text: "Bleeding risk" }]);
      }
      return jsonResponse([], 404);
    });

    const bundle = await new ApiClient("/api", "/local-api").fetchBundle({
      id: "warfarin",
      name_en: "Warfarin",
      paths: {
        substance: "substances/by-id/wa/warfarin.json",
        safety_warnings: "safety-warnings/by-substance/wa/warfarin.json",
      },
    });

    expect(bundle.safetyWarnings).toHaveLength(1);
    expect(bundle.safetyWarnings[0].warning_text).toBe("Bleeding risk");
  });
});

function jsonResponse(payload: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}
