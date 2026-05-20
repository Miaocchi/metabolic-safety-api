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
});

function jsonResponse(payload: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}
