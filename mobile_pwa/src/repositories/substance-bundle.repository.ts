/**
 * @module repositories/substance-bundle.repository
 *
 * IndexedDB-backed substance bundle cache repository.
 * Wraps existing db.ts functions behind the SubstanceBundleRepository interface.
 */
import type { OfflineCacheRecord, SubstanceBundle } from "../types";
import { cacheBundle, getCachedBundle, getCachedBundleIds } from "../lib/db";
import type { SubstanceBundleRepository } from "./interfaces";

export class IndexedDBSubstanceBundleRepository implements SubstanceBundleRepository {
  async getById(id: string): Promise<SubstanceBundle | undefined> {
    return getCachedBundle(id);
  }

  async save(bundle: SubstanceBundle): Promise<void> {
    await cacheBundle(bundle);
  }

  async listCached(): Promise<OfflineCacheRecord<SubstanceBundle>[]> {
    return getCachedBundleIds() as Promise<OfflineCacheRecord<SubstanceBundle>[]>;
  }
}
