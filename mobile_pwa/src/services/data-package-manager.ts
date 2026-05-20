/**
 * @module services/data-package-manager
 *
 * Centralizes manifest tracking, data versioning, privacy note display,
 * cache invalidation status, and sync coordination.
 *
 * This is the single source of truth for "what data version is loaded?"
 * and "is the local cache stale?"
 */
import type { ApiManifest, StaticDbStats } from "../types";
import type { StaticCacheRepository } from "../repositories/interfaces";

// ── Types ─────────────────────────────────────────────────────────────

export interface DataPackageStatus {
  /** Whether a manifest has been loaded from the remote API. */
  connected: boolean;
  /** The dataset version string from the manifest, if available. */
  datasetVersion: string | null;
  /** The API version string from the manifest, if available. */
  apiVersion: string | null;
  /** The manifest's privacy note, if present. */
  privacyNote: string | null;
  /** The manifest's warning, if present. */
  warning: string | null;
  /** Timestamp of the last successful sync, or null. */
  lastSyncAt: number | null;
  /** Source URL of the last sync, or null. */
  syncSource: string | null;
  /** Count of cached search shards. */
  searchShards: number;
  /** Count of cached substance bundles. */
  bundles: number;
  /** Count of cached JSON files. */
  jsonFiles: number;
  /** Count of cached manifests. */
  manifests: number;
  /** Offline package info, if available in the manifest. */
  offlinePackage: OfflinePackageInfo | null;
  /** Whether the cache appears stale (has data but no recent sync). */
  cacheStale: boolean;
}

export interface OfflinePackageInfo {
  manifestPath: string | null;
  zipPath: string | null;
  zipBytes: number | null;
  zipSha256: string | null;
}

export interface SyncResult {
  manifest: ApiManifest;
  shardKeys: string[];
  datasetVersion: string | null;
}

// ── Constants ─────────────────────────────────────────────────────────

/** Default cache staleness threshold: 7 days in ms. */
const STALE_THRESHOLD_MS = 7 * 24 * 60 * 60 * 1000;

/** Default common shard keys to always sync. */
export const COMMON_SHARD_KEYS = ["ib", "wa", "ca", "se", "me", "pa", "am", "al", "co", "in"];

// ── DataPackageManager ────────────────────────────────────────────────

export class DataPackageManager {
  private manifest: ApiManifest | null = null;
  private readonly cacheRepo: StaticCacheRepository;
  private readonly staleThresholdMs: number;

  constructor(cacheRepo: StaticCacheRepository, staleThresholdMs = STALE_THRESHOLD_MS) {
    this.cacheRepo = cacheRepo;
    this.staleThresholdMs = staleThresholdMs;
  }

  /**
   * Updates the in-memory manifest reference.
   * Called after a successful manifest fetch.
   */
  setManifest(manifest: ApiManifest): void {
    this.manifest = manifest;
  }

  /**
   * Returns the current manifest, if loaded.
   */
  getManifest(): ApiManifest | null {
    return this.manifest;
  }

  /**
   * Extracts the privacy note from the manifest.
   * Returns null if not present.
   */
  getPrivacyNote(): string | null {
    return this.manifest?.privacy_note || null;
  }

  /**
   * Extracts the warning from the manifest.
   * Returns null if not present.
   */
  getWarning(): string | null {
    return this.manifest?.warning || null;
  }

  /**
   * Returns the dataset version string.
   */
  getDatasetVersion(): string | null {
    return this.manifest?.dataset_version || null;
  }

  /**
   * Returns the API version string.
   */
  getApiVersion(): string | null {
    return this.manifest?.api_version || null;
  }

  /**
   * Extracts offline package info from the manifest.
   * Checks both top-level and online_library paths.
   */
  getOfflinePackageInfo(): OfflinePackageInfo | null {
    const pkg = this.manifest?.online_library?.full_package || this.manifest?.full_package;
    if (!pkg) return null;
    return {
      manifestPath: pkg.manifest || null,
      zipPath: pkg.zip || null,
      zipBytes: pkg.zip_bytes ?? null,
      zipSha256: pkg.zip_sha256 || null,
    };
  }

  /**
   * Returns substance count from the manifest.
   */
  getSubstanceCount(): number {
    return this.manifest?.counts?.substances || 0;
  }

  /**
   * Returns interaction count from the manifest.
   */
  getInteractionCount(): number {
    return this.manifest?.counts?.interactions || 0;
  }

  /**
   * Returns dose candidate count from the manifest.
   */
  getDoseCandidateCount(): number {
    return this.manifest?.counts?.dose_candidates || 0;
  }

  /**
   * Builds a full DataPackageStatus by combining the in-memory manifest
   * with persisted cache stats from the repository.
   */
  async getStatus(): Promise<DataPackageStatus> {
    let stats: StaticDbStats;
    try {
      stats = await this.cacheRepo.getStats();
    } catch {
      stats = { manifests: 0, searchShards: 0, bundles: 0, jsonFiles: 0 };
    }

    const connected = !!this.manifest;
    const lastSyncAt = stats.lastSyncAt ?? null;
    const hasData = stats.jsonFiles > 0 || stats.bundles > 0;
    // Data without a recorded sync timestamp has unknown freshness — treat as stale.
    const cacheStale = hasData && (lastSyncAt === null || Date.now() - lastSyncAt > this.staleThresholdMs);

    return {
      connected,
      datasetVersion: this.manifest?.dataset_version || stats.datasetVersion || null,
      apiVersion: this.manifest?.api_version || null,
      privacyNote: this.getPrivacyNote(),
      warning: this.getWarning(),
      lastSyncAt,
      syncSource: stats.source || null,
      searchShards: stats.searchShards,
      bundles: stats.bundles,
      jsonFiles: stats.jsonFiles,
      manifests: stats.manifests,
      offlinePackage: this.getOfflinePackageInfo(),
      cacheStale,
    };
  }

  /**
   * Records a successful sync in the repository.
   */
  async recordSync(options: { source: string; datasetVersion?: string; manifests: number; searchShards: number }): Promise<void> {
    await this.cacheRepo.saveSyncState({
      lastSyncAt: Date.now(),
      source: options.source,
      datasetVersion: options.datasetVersion,
      manifests: options.manifests,
      searchShards: options.searchShards,
    });
  }

  /**
   * Clears all cached data and resets the manifest.
   */
  async clearCache(): Promise<void> {
    await this.cacheRepo.clearAll();
    this.manifest = null;
  }

  /**
   * Returns the default offline package download URL given a base API URL.
   */
  buildOfflinePackageUrl(apiBase: string): string | null {
    const info = this.getOfflinePackageInfo();
    if (!info?.zipPath) return null;
    const cleanBase = apiBase.replace(/\/+$/, "");
    const cleanPath = String(info.zipPath).replace(/^\/?api\//, "").replace(/^\//, "");
    return `${cleanBase}/${cleanPath}`;
  }

  /**
   * Determines which shard keys should be synced based on options.
   */
  resolveShardKeys(options: { shardKeys?: string[]; includeCommonShards?: boolean; manifest?: { shards?: Record<string, number> } }): string[] {
    const common = options.includeCommonShards === false ? [] : COMMON_SHARD_KEYS;
    const requested = options.shardKeys || [];
    const manifest = options.manifest || this.manifest;
    const shards = (manifest as { shards?: Record<string, number> })?.shards;
    const allKeys = [...new Set([...requested, ...common])];
    if (shards) {
      return allKeys.filter((key) => shards[key] !== undefined);
    }
    return allKeys;
  }
}
