/**
 * @module repositories/interfaces
 *
 * Repository interfaces for the data access layer.
 * Each repository abstracts a specific domain aggregate.
 */
import type {
  JournalEntry,
  OfflineCacheRecord,
  PwaSettings,
  StaticDbStats,
  SubstanceBundle,
  UserProfile,
} from "../types";

// ── Journal Repository ────────────────────────────────────────────────

export interface JournalRepository {
  /** Returns all journal entries sorted by timestamp descending. */
  getAll(): Promise<JournalEntry[]>;
  /** Saves (upserts) a journal entry. */
  save(entry: JournalEntry): Promise<void>;
  /** Deletes a journal entry by id. */
  delete(id: string): Promise<void>;
  /** Deletes all journal entries. */
  clear(): Promise<void>;
}

// ── Substance Bundle Repository ───────────────────────────────────────

export interface SubstanceBundleRepository {
  /** Returns a cached bundle by substance id, or undefined. */
  getById(id: string): Promise<SubstanceBundle | undefined>;
  /** Saves (upserts) a substance bundle. */
  save(bundle: SubstanceBundle): Promise<void>;
  /** Returns all cached bundle records sorted by updatedAt descending. */
  listCached(): Promise<OfflineCacheRecord<SubstanceBundle>[]>;
}

// ── Settings Repository ───────────────────────────────────────────────

export interface SettingsRepository {
  /** Loads the user profile, or undefined if not set. */
  loadProfile(): Promise<UserProfile | undefined>;
  /** Saves the user profile. */
  saveProfile(profile: UserProfile): Promise<void>;
  /** Loads PWA settings, or undefined if not set. */
  loadSettings(): Promise<PwaSettings | undefined>;
  /** Saves PWA settings. */
  saveSettings(settings: PwaSettings): Promise<void>;
}

// ── Static Cache Repository ───────────────────────────────────────────

export interface StaticCacheRepository {
  /** Caches a static JSON response by path. */
  cacheJson<T>(path: string, value: T, source?: string): Promise<void>;
  /** Returns a cached static JSON response, or undefined. */
  getCachedJson<T>(path: string): Promise<T | undefined>;
  /** Returns aggregate static database stats. */
  getStats(): Promise<StaticDbStats>;
  /** Saves partial sync state. */
  saveSyncState(state: Partial<StaticDbStats>): Promise<void>;
  /** Clears all static cache data (json + bundles + sync state). */
  clearAll(): Promise<void>;
}
