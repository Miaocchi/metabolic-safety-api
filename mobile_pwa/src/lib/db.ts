/**
 * @module lib/db
 *
 * IndexedDB persistence — IO layer for journal, cache, and settings storage.
 *
 * NOTE: The repository layer (`repositories/`) provides the canonical
 * abstraction for IndexedDB access. All four repository classes
 * (journal, settings, substance-bundle, static-cache) wrap these functions.
 * New code should prefer injecting repository instances via the interfaces
 * in `repositories/interfaces.ts`.
 */
import type { JournalEntry, OfflineCacheRecord, PwaSettings, StaticDbStats, SubstanceBundle, UserProfile } from "../types";

const DB_NAME = "metabolic_safety_mobile_pwa";
const DB_VERSION = 1;

type StoreName = "journal" | "cache" | "settings";

function openDb() {
  return new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains("journal")) db.createObjectStore("journal", { keyPath: "id" });
      if (!db.objectStoreNames.contains("cache")) db.createObjectStore("cache", { keyPath: "key" });
      if (!db.objectStoreNames.contains("settings")) db.createObjectStore("settings", { keyPath: "key" });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function tx<T>(storeName: StoreName, mode: IDBTransactionMode, run: (store: IDBObjectStore) => IDBRequest<T>) {
  const db = await openDb();
  return new Promise<T>((resolve, reject) => {
    const transaction = db.transaction(storeName, mode);
    const request = run(transaction.objectStore(storeName));
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    transaction.oncomplete = () => db.close();
    transaction.onerror = () => {
      db.close();
      reject(transaction.error);
    };
  });
}

export async function allJournal() {
  const rows = await tx<JournalEntry[]>("journal", "readonly", (store) => store.getAll());
  return rows.sort((a, b) => b.timestamp - a.timestamp);
}

export async function saveJournalEntry(entry: JournalEntry) {
  await tx<IDBValidKey>("journal", "readwrite", (store) => store.put(entry));
}

export async function deleteJournalEntry(id: string) {
  await tx<undefined>("journal", "readwrite", (store) => store.delete(id));
}

export async function clearJournal() {
  await tx<undefined>("journal", "readwrite", (store) => store.clear());
}

export async function cacheBundle(bundle: SubstanceBundle) {
  const record: OfflineCacheRecord<SubstanceBundle> = {
    key: `bundle:${bundle.detail.id}`,
    value: normalizeBundle(bundle),
    updatedAt: Date.now(),
  };
  await tx<IDBValidKey>("cache", "readwrite", (store) => store.put(record));
}

export async function cacheStaticJson<T>(path: string, value: T, source?: string) {
  const record: OfflineCacheRecord<T> = {
    key: `json:${normalizeStaticPath(path)}`,
    value,
    updatedAt: Date.now(),
    source,
  };
  await tx<IDBValidKey>("cache", "readwrite", (store) => store.put(record));
}

export async function getCachedStaticJson<T>(path: string) {
  const record = await tx<OfflineCacheRecord<T> | undefined>("cache", "readonly", (store) => store.get(`json:${normalizeStaticPath(path)}`));
  return record?.value;
}

export async function getCachedBundle(id: string) {
  const record = await tx<OfflineCacheRecord<SubstanceBundle> | undefined>("cache", "readonly", (store) => store.get(`bundle:${id}`));
  return normalizeBundle(record?.value);
}

export async function getCachedBundleIds() {
  const rows = await tx<OfflineCacheRecord[]>("cache", "readonly", (store) => store.getAll());
  return rows.filter((row) => row.key.startsWith("bundle:")).sort((a, b) => b.updatedAt - a.updatedAt);
}

export async function saveStaticDbSyncState(value: Partial<StaticDbStats>) {
  await tx<IDBValidKey>("settings", "readwrite", (store) => store.put({ key: "static-db-sync", value, updatedAt: Date.now() }));
}

export async function getStaticDbStats() {
  const [cacheRows, syncState] = await Promise.all([
    tx<OfflineCacheRecord[]>("cache", "readonly", (store) => store.getAll()),
    tx<OfflineCacheRecord<Partial<StaticDbStats>> | undefined>("settings", "readonly", (store) => store.get("static-db-sync")),
  ]);
  const jsonFiles = cacheRows.filter((row) => row.key.startsWith("json:"));
  const bundles = cacheRows.filter((row) => row.key.startsWith("bundle:"));
  const searchShards = jsonFiles.filter((row) => row.key.startsWith("json:search/shards/"));
  const manifests = jsonFiles.filter((row) => row.key === "json:manifest.json" || row.key.endsWith("/manifest.json"));
  return {
    manifests: manifests.length,
    searchShards: searchShards.length,
    bundles: bundles.length,
    jsonFiles: jsonFiles.length,
    ...syncState?.value,
  } satisfies StaticDbStats;
}

export async function clearStaticDatabase() {
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const transaction = db.transaction(["cache", "settings"], "readwrite");
    const cacheStore = transaction.objectStore("cache");
    const settingsStore = transaction.objectStore("settings");
    const keysRequest = cacheStore.getAllKeys();
    keysRequest.onsuccess = () => {
      for (const key of keysRequest.result) {
        const text = String(key);
        if (text.startsWith("json:") || text.startsWith("bundle:")) cacheStore.delete(key);
      }
      settingsStore.delete("static-db-sync");
    };
    keysRequest.onerror = () => reject(keysRequest.error);
    transaction.oncomplete = () => {
      db.close();
      resolve();
    };
    transaction.onerror = () => {
      db.close();
      reject(transaction.error);
    };
  });
}

export async function saveProfile(profile: UserProfile) {
  await tx<IDBValidKey>("settings", "readwrite", (store) => store.put({ key: "profile", value: profile, updatedAt: Date.now() }));
}

export async function loadProfile() {
  const row = await tx<OfflineCacheRecord<UserProfile> | undefined>("settings", "readonly", (store) => store.get("profile"));
  return row?.value;
}

export async function saveSettings(settings: PwaSettings) {
  await tx<IDBValidKey>("settings", "readwrite", (store) => store.put({ key: "pwa-settings", value: settings, updatedAt: Date.now() }));
}

export async function loadSettings() {
  const row = await tx<OfflineCacheRecord<PwaSettings> | undefined>("settings", "readonly", (store) => store.get("pwa-settings"));
  return row?.value;
}

function normalizeStaticPath(path: string) {
  return String(path || "").replace(/^\/?api\//, "").replace(/^\//, "");
}

function normalizeBundle(bundle: SubstanceBundle): SubstanceBundle;
function normalizeBundle(bundle: Partial<SubstanceBundle> | undefined): SubstanceBundle | undefined;
function normalizeBundle(bundle?: Partial<SubstanceBundle>): SubstanceBundle | undefined {
  if (!bundle?.detail) return undefined;
  return {
    ...bundle,
    detail: bundle.detail,
    interactions: Array.isArray(bundle.interactions) ? bundle.interactions : [],
    doseRules: Array.isArray(bundle.doseRules) ? bundle.doseRules : [],
    doseCandidates: Array.isArray(bundle.doseCandidates) ? bundle.doseCandidates : [],
    overdoseWarnings: Array.isArray(bundle.overdoseWarnings) ? bundle.overdoseWarnings : [],
    drugEffects: Array.isArray(bundle.drugEffects) ? bundle.drugEffects : [],
    pharmacokinetics: Array.isArray(bundle.pharmacokinetics) ? bundle.pharmacokinetics : [],
    enzymeRelations: Array.isArray(bundle.enzymeRelations) ? bundle.enzymeRelations : [],
    labelSections: Array.isArray(bundle.labelSections) ? bundle.labelSections : [],
    safetyWarnings: Array.isArray(bundle.safetyWarnings) ? bundle.safetyWarnings : [],
    interactionSignals: Array.isArray(bundle.interactionSignals) ? bundle.interactionSignals : [],
    foodInteractions: Array.isArray(bundle.foodInteractions) ? bundle.foodInteractions : [],
    adverseSignals: Array.isArray(bundle.adverseSignals) ? bundle.adverseSignals : [],
    pgx: Array.isArray(bundle.pgx) ? bundle.pgx : [],
    fetchedAt: typeof bundle.fetchedAt === "number" ? bundle.fetchedAt : Date.now(),
  } satisfies SubstanceBundle;
}
