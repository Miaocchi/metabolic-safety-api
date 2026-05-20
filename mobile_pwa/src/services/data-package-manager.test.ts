import { describe, expect, it, vi, beforeEach } from "vitest";
import { DataPackageManager, COMMON_SHARD_KEYS } from "./data-package-manager";
import type { StaticCacheRepository } from "../repositories/interfaces";
import type { ApiManifest, StaticDbStats } from "../types";

function mockCacheRepo(overrides: Partial<StaticCacheRepository> = {}): StaticCacheRepository {
  return {
    cacheJson: vi.fn().mockResolvedValue(undefined),
    getCachedJson: vi.fn().mockResolvedValue(undefined),
    getStats: vi.fn().mockResolvedValue({
      manifests: 0,
      searchShards: 0,
      bundles: 0,
      jsonFiles: 0,
    } satisfies StaticDbStats),
    saveSyncState: vi.fn().mockResolvedValue(undefined),
    clearAll: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}

const sampleManifest: ApiManifest = {
  api_version: "1.0",
  dataset_version: "2026.05.17",
  generated_at: "2026-05-17T00:00:00Z",
  counts: { substances: 1200, interactions: 450, dose_candidates: 300 },
  privacy_note: "所有数据仅存于本机 IndexedDB。",
  warning: "这不是临床决策支持工具。",
  full_package: {
    manifest: "api/full_package/manifest.json",
    zip: "api/full_package/data.zip",
    zip_bytes: 5242880,
    zip_sha256: "abc123",
  },
};

describe("services/DataPackageManager", () => {
  let repo: StaticCacheRepository;
  let manager: DataPackageManager;

  beforeEach(() => {
    repo = mockCacheRepo();
    manager = new DataPackageManager(repo);
  });

  describe("manifest management", () => {
    it("starts with null manifest", () => {
      expect(manager.getManifest()).toBeNull();
    });

    it("stores and retrieves manifest", () => {
      manager.setManifest(sampleManifest);
      expect(manager.getManifest()).toBe(sampleManifest);
    });

    it("extracts dataset version", () => {
      manager.setManifest(sampleManifest);
      expect(manager.getDatasetVersion()).toBe("2026.05.17");
    });

    it("returns null dataset version when no manifest", () => {
      expect(manager.getDatasetVersion()).toBeNull();
    });

    it("extracts API version", () => {
      manager.setManifest(sampleManifest);
      expect(manager.getApiVersion()).toBe("1.0");
    });

    it("extracts counts", () => {
      manager.setManifest(sampleManifest);
      expect(manager.getSubstanceCount()).toBe(1200);
      expect(manager.getInteractionCount()).toBe(450);
      expect(manager.getDoseCandidateCount()).toBe(300);
    });

    it("returns 0 counts when no manifest", () => {
      expect(manager.getSubstanceCount()).toBe(0);
      expect(manager.getInteractionCount()).toBe(0);
    });
  });

  describe("privacy and warning", () => {
    it("extracts privacy note from manifest", () => {
      manager.setManifest(sampleManifest);
      expect(manager.getPrivacyNote()).toBe("所有数据仅存于本机 IndexedDB。");
    });

    it("returns null privacy note when no manifest", () => {
      expect(manager.getPrivacyNote()).toBeNull();
    });

    it("extracts warning from manifest", () => {
      manager.setManifest(sampleManifest);
      expect(manager.getWarning()).toBe("这不是临床决策支持工具。");
    });

    it("returns null warning when no manifest", () => {
      expect(manager.getWarning()).toBeNull();
    });
  });

  describe("offline package", () => {
    it("extracts offline package info", () => {
      manager.setManifest(sampleManifest);
      const info = manager.getOfflinePackageInfo();
      expect(info).not.toBeNull();
      expect(info!.zipPath).toBe("api/full_package/data.zip");
      expect(info!.zipBytes).toBe(5242880);
      expect(info!.zipSha256).toBe("abc123");
    });

    it("checks online_library path too", () => {
      manager.setManifest({
        online_library: {
          full_package: {
            zip: "api/online/data.zip",
            zip_bytes: 1024,
          },
        },
      });
      const info = manager.getOfflinePackageInfo();
      expect(info!.zipPath).toBe("api/online/data.zip");
    });

    it("returns null when no package info", () => {
      manager.setManifest({});
      expect(manager.getOfflinePackageInfo()).toBeNull();
    });

    it("builds download URL", () => {
      manager.setManifest(sampleManifest);
      const url = manager.buildOfflinePackageUrl("https://example.com/api");
      expect(url).toBe("https://example.com/api/full_package/data.zip");
    });

    it("returns null URL when no package", () => {
      manager.setManifest({});
      expect(manager.buildOfflinePackageUrl("https://example.com")).toBeNull();
    });
  });

  describe("status", () => {
    it("returns disconnected status without manifest", async () => {
      const status = await manager.getStatus();
      expect(status.connected).toBe(false);
      expect(status.datasetVersion).toBeNull();
      expect(status.privacyNote).toBeNull();
    });

    it("returns connected status with manifest", async () => {
      manager.setManifest(sampleManifest);
      const status = await manager.getStatus();
      expect(status.connected).toBe(true);
      expect(status.datasetVersion).toBe("2026.05.17");
      expect(status.privacyNote).toContain("IndexedDB");
      expect(status.offlinePackage).not.toBeNull();
    });

    it("detects stale cache", async () => {
      repo = mockCacheRepo({
        getStats: vi.fn().mockResolvedValue({
          manifests: 1,
          searchShards: 10,
          bundles: 5,
          jsonFiles: 50,
          lastSyncAt: Date.now() - 8 * 24 * 60 * 60 * 1000, // 8 days ago
          datasetVersion: "old",
        }),
      });
      manager = new DataPackageManager(repo);
      const status = await manager.getStatus();
      expect(status.cacheStale).toBe(true);
    });

    it("does not flag fresh cache as stale", async () => {
      repo = mockCacheRepo({
        getStats: vi.fn().mockResolvedValue({
          manifests: 1,
          searchShards: 10,
          bundles: 5,
          jsonFiles: 50,
          lastSyncAt: Date.now() - 1000, // 1 second ago
        }),
      });
      manager = new DataPackageManager(repo);
      const status = await manager.getStatus();
      expect(status.cacheStale).toBe(false);
    });

    it("does not flag empty cache as stale", async () => {
      repo = mockCacheRepo({
        getStats: vi.fn().mockResolvedValue({
          manifests: 0,
          searchShards: 0,
          bundles: 0,
          jsonFiles: 0,
        }),
      });
      manager = new DataPackageManager(repo);
      const status = await manager.getStatus();
      expect(status.cacheStale).toBe(false);
    });

    it("flags data without sync timestamp as stale", async () => {
      repo = mockCacheRepo({
        getStats: vi.fn().mockResolvedValue({
          manifests: 0,
          searchShards: 5,
          bundles: 3,
          jsonFiles: 20,
          // no lastSyncAt — data from unknown source/time
        }),
      });
      manager = new DataPackageManager(repo);
      const status = await manager.getStatus();
      expect(status.cacheStale).toBe(true);
    });
  });

  describe("sync recording", () => {
    it("records sync state", async () => {
      await manager.recordSync({
        source: "https://example.com/api",
        datasetVersion: "2026.05.17",
        manifests: 2,
        searchShards: 10,
      });
      expect(repo.saveSyncState).toHaveBeenCalledWith(
        expect.objectContaining({
          source: "https://example.com/api",
          datasetVersion: "2026.05.17",
          manifests: 2,
          searchShards: 10,
          lastSyncAt: expect.any(Number),
        }),
      );
    });
  });

  describe("cache clearing", () => {
    it("clears cache and resets manifest", async () => {
      manager.setManifest(sampleManifest);
      await manager.clearCache();
      expect(repo.clearAll).toHaveBeenCalled();
      expect(manager.getManifest()).toBeNull();
    });
  });

  describe("resolveShardKeys", () => {
    it("includes common shards by default", () => {
      const keys = manager.resolveShardKeys({});
      for (const key of COMMON_SHARD_KEYS) {
        expect(keys).toContain(key);
      }
    });

    it("excludes common shards when opted out", () => {
      const keys = manager.resolveShardKeys({ includeCommonShards: false });
      expect(keys).toEqual([]);
    });

    it("filters by manifest shards when available", () => {
      manager.setManifest({ shards: { wa: 1, ib: 1 } } as unknown as ApiManifest);
      const keys = manager.resolveShardKeys({});
      expect(keys).toContain("wa");
      expect(keys).toContain("ib");
      // ca should be filtered out since it's not in manifest shards
      expect(keys).not.toContain("ca");
    });

    it("includes custom shard keys", () => {
      const keys = manager.resolveShardKeys({ shardKeys: ["xx", "yy"] });
      expect(keys).toContain("xx");
      expect(keys).toContain("yy");
    });
  });
});
