/**
 * @module services/substance-service
 *
 * Domain service façade for substance/bundle operations.
 * Coordinates between the substance bundle repository and the ApiClient.
 */
import type { SubstanceBundle, SubstanceSummary } from "../types";
import type { SubstanceBundleRepository } from "../repositories/interfaces";
import type { ApiClient } from "../lib/api";

// ── SubstanceService ──────────────────────────────────────────────────

export class SubstanceService {
  private readonly bundleRepo: SubstanceBundleRepository;
  private readonly api: ApiClient;

  constructor(bundleRepo: SubstanceBundleRepository, api: ApiClient) {
    this.bundleRepo = bundleRepo;
    this.api = api;
  }

  /**
   * Searches substances via the API.
   */
  async search(query: string): Promise<SubstanceSummary[]> {
    return this.api.search(query);
  }

  /**
   * Fetches a substance bundle, with cache-first strategy.
   * Returns the cached version if available, then fetches fresh data.
   */
  async fetchBundle(item: SubstanceSummary): Promise<SubstanceBundle> {
    const bundle = await this.api.fetchBundle(item);
    await this.bundleRepo.save(bundle);
    return bundle;
  }

  /**
   * Returns a cached bundle by id, or undefined.
   */
  async getCachedBundle(id: string): Promise<SubstanceBundle | undefined> {
    return this.bundleRepo.getById(id);
  }

  /**
   * Hydrates the bundle cache map from IndexedDB.
   * Returns a record of substanceId → SubstanceBundle.
   */
  async hydrateBundleCache(maxItems = 80): Promise<Record<string, SubstanceBundle>> {
    const records = await this.bundleRepo.listCached();
    const result: Record<string, SubstanceBundle> = {};
    await Promise.all(
      records.slice(0, maxItems).map(async (record) => {
        const id = record.key.replace(/^bundle:/, "");
        const cached = await this.bundleRepo.getById(id);
        if (cached?.detail?.id) result[cached.detail.id] = cached;
      }),
    );
    return result;
  }

  /**
   * Saves a substance bundle to the cache.
   */
  async cacheBundle(bundle: SubstanceBundle): Promise<void> {
    await this.bundleRepo.save(bundle);
  }

  /**
   * Creates an empty SubstanceBundle shell for a substance summary.
   * Used when fetching fails and we need a placeholder.
   */
  createEmptyBundle(item: SubstanceSummary, datasetVersion?: string): SubstanceBundle {
    return {
      detail: { ...item, dataset_version: datasetVersion },
      interactions: [],
      doseRules: [],
      doseCandidates: [],
      overdoseWarnings: [],
      drugEffects: [],
      pharmacokinetics: [],
      enzymeRelations: [],
      labelSections: [],
      safetyWarnings: [],
      interactionSignals: [],
      foodInteractions: [],
      adverseSignals: [],
      pgx: [],
      fetchedAt: Date.now(),
    };
  }
}
