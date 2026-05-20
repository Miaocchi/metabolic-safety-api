/**
 * @module repositories/static-cache.repository
 *
 * IndexedDB-backed static cache repository.
 * Wraps existing db.ts functions behind the StaticCacheRepository interface.
 */
import type { StaticDbStats } from "../types";
import { cacheStaticJson, getCachedStaticJson, getStaticDbStats, saveStaticDbSyncState, clearStaticDatabase } from "../lib/db";
import type { StaticCacheRepository } from "./interfaces";

export class IndexedDBStaticCacheRepository implements StaticCacheRepository {
  async cacheJson<T>(path: string, value: T, source?: string): Promise<void> {
    await cacheStaticJson(path, value, source);
  }

  async getCachedJson<T>(path: string): Promise<T | undefined> {
    return getCachedStaticJson<T>(path);
  }

  async getStats(): Promise<StaticDbStats> {
    return getStaticDbStats();
  }

  async saveSyncState(state: Partial<StaticDbStats>): Promise<void> {
    await saveStaticDbSyncState(state);
  }

  async clearAll(): Promise<void> {
    await clearStaticDatabase();
  }
}
