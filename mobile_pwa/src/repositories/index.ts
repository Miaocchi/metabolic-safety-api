/**
 * @module repositories
 *
 * Repository layer barrel export.
 * Provides typed data access abstractions backed by IndexedDB.
 */
export type {
  JournalRepository,
  SubstanceBundleRepository,
  SettingsRepository,
  StaticCacheRepository,
} from "./interfaces";

export { IndexedDBJournalRepository } from "./journal.repository";
export { IndexedDBSubstanceBundleRepository } from "./substance-bundle.repository";
export { IndexedDBSettingsRepository } from "./settings.repository";
export { IndexedDBStaticCacheRepository } from "./static-cache.repository";
