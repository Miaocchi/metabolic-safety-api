/**
 * @module lib/api
 *
 * API client — IO layer for fetching static API data and local backend.
 *
 * NOTE: The repository layer (`repositories/`) and service layer (`services/`)
 * provide the canonical abstraction for data access. New code should prefer
 * injecting repository/service instances rather than importing ApiClient directly.
 * This module remains the backing implementation for backward compatibility.
 */
import type {
  AdverseSignalRow,
  ApiManifest,
  DoseRule,
  EvidenceTextRow,
  FoodInteractionRow,
  InteractionRow,
  InteractionSignalRow,
  LabelSectionRow,
  LocalSeedPayload,
  PharmacokineticRow,
  PgxRow,
  SafetyWarningRow,
  SearchManifest,
  SubstanceBundle,
  SubstanceDetail,
  SubstanceSummary,
} from "../types";
import { cacheStaticJson, getCachedStaticJson, saveStaticDbSyncState } from "./db";
import { displayName, scoreItem, searchShardKeysForQuery } from "./format";

const DEFAULT_API_BASE = "/api";
const DEFAULT_LOCAL_API_BASE = "/local-api";

export class ApiClient {
  readonly apiBase: string;
  readonly localApiBase: string;
  private searchManifest?: SearchManifest;
  private shardCache = new Map<string, SubstanceSummary[]>();

  constructor(apiBase = DEFAULT_API_BASE, localApiBase = DEFAULT_LOCAL_API_BASE) {
    this.apiBase = apiBase.replace(/\/+$/, "");
    this.localApiBase = localApiBase.replace(/\/+$/, "");
  }

  async fetchManifest() {
    return this.fetchJson<ApiManifest>("manifest.json");
  }

  async fetchSearchManifest() {
    if (!this.searchManifest) this.searchManifest = await this.fetchJson<SearchManifest>("search/manifest.json");
    return this.searchManifest;
  }

  async search(query: string) {
    const q = query.trim();
    if (!q) return [];
    const manifest = await this.fetchSearchManifest().catch(() => null);
    const keys = searchShardKeysForQuery(q);
    const batches = await Promise.all(keys.map((key) => this.fetchSearchShard(key, manifest || undefined)));
    const byId = new Map<string, SubstanceSummary>();
    for (const row of batches.flat()) byId.set(row.id, row);
    return [...byId.values()]
      .map((item) => ({ item, score: scoreItem(item, q) }))
      .filter((row) => row.score > 0)
      .sort((a, b) => b.score - a.score || displayName(a.item).localeCompare(displayName(b.item), "zh-CN"))
      .slice(0, 80)
      .map((row) => row.item);
  }

  async fetchBundle(item: SubstanceSummary) {
    const detail = await this.fetchJson<SubstanceDetail>(item.paths?.substance || item.paths?.["substance"] || "");
    const paths = { ...(item.paths || {}), ...(detail.paths || {}) };
    const [interactions, doseRules, doseCandidates, overdoseWarnings, drugEffects, pharmacokinetics, enzymeRelations, labelSections, safetyWarnings, interactionSignals, foodInteractions, adverseSignalsRows, pgx] =
      await Promise.all([
        this.safeFetch<InteractionRow>(paths.interactions),
        this.safeFetch<DoseRule>(paths.dose_rules),
        this.safeFetch<EvidenceTextRow>(paths.dose_candidates),
        this.safeFetch<EvidenceTextRow>(paths.overdose_warnings),
        this.safeFetch<EvidenceTextRow>(paths.drug_effects),
        this.safeFetch<PharmacokineticRow>(paths.pharmacokinetics),
        this.safeFetch<EvidenceTextRow>(paths.enzyme_relations),
        this.safeFetch<LabelSectionRow>(paths.label_sections),
        this.safeFetch<SafetyWarningRow>(paths.safety_warnings),
        this.safeFetch<InteractionSignalRow>(paths.interaction_signals),
        this.safeFetch<FoodInteractionRow>(paths.food_interactions),
        this.safeFetch<AdverseSignalRow>(paths.adverse_signals),
        this.safeFetch<PgxRow>(paths.pgx),
      ]);
    const mergedDetail = mergePharmacokineticsIntoDetail(detail, pharmacokinetics);
    return {
      detail: mergedDetail,
      interactions,
      doseRules,
      doseCandidates,
      overdoseWarnings,
      drugEffects,
      pharmacokinetics,
      enzymeRelations,
      labelSections,
      safetyWarnings,
      interactionSignals,
      foodInteractions,
      adverseSignals: adverseSignalsRows,
      pgx,
      fetchedAt: Date.now(),
    } satisfies SubstanceBundle;
  }

  async checkLocal(ids: string[]) {
    if (!ids.length) return [];
    const url = `${this.localApiBase}/check?ids=${encodeURIComponent(ids.join(","))}`;
    const response = await fetch(url, { cache: "no-cache" });
    if (!response.ok) throw new Error(`本地后台检查失败 HTTP ${response.status}`);
    const payload = await response.json();
    if (Array.isArray(payload)) return payload as InteractionRow[];
    if (Array.isArray(payload?.risks)) return payload.risks as InteractionRow[];
    if (Array.isArray(payload?.interactions)) return payload.interactions as InteractionRow[];
    return [];
  }

  /**
   * Fetches adverse signal data for the given substances.
   *
   * Always tries static/cached signals first. Only falls back to live
   * openFDA API calls when `options.liveFallback` is explicitly true
   * (opt-in user consent), because the live endpoint sends substance
   * names/aliases to a third-party service.
   */
  async adverseSignals(items: SubstanceSummary[], limit = 3, options: { liveFallback?: boolean } = {}) {
    const cleanItems = [...new Map(items.filter((item) => item?.id).map((item) => [item.id, item])).values()].sort((a, b) => a.id.localeCompare(b.id));
    const cleanIds = cleanItems.map((item) => item.id);
    if (!cleanIds.length) return [] as unknown[];
    const staticRows = await Promise.all(cleanIds.map((id) => this.fetchStaticAdverseSignal(id)));
    const staticItems = staticRows.flat();
    if (staticItems.length) return staticItems;
    if (!options.liveFallback) return [];
    const directRows = await Promise.all(cleanItems.map((item) => this.fetchOpenFdaSignals(item, limit).catch(() => null)));
    return directRows.filter(Boolean);
  }

  private async fetchStaticAdverseSignal(id: string) {
    const rows = await this.safeFetch<unknown>(`adverse_signals/${encodeURIComponent(id)}.json`);
    return rows.flatMap((row) => {
      if (Array.isArray(row)) return row;
      const payload = row as { items?: unknown[]; signals?: unknown[]; rows?: unknown[] } | null;
      if (Array.isArray(payload?.items)) return payload.items;
      if (Array.isArray(payload?.signals)) return payload.signals;
      if (Array.isArray(payload?.rows)) return payload.rows;
      return row ? [row] : [];
    });
  }

  private async fetchOpenFdaSignals(item: SubstanceSummary, limit: number) {
    const terms = [item.name_en, item.name_zh, item.id, ...(Array.isArray(item.aliases) ? item.aliases : [])]
      .map((value) => String(value || "").trim())
      .filter(Boolean)
      .slice(0, 4);
    for (const term of terms) {
      const escaped = term.replace(/"/g, "");
      const search = [
        `patient.drug.openfda.generic_name:\"${escaped}\"`,
        `patient.drug.openfda.brand_name:\"${escaped}\"`,
        `patient.drug.openfda.substance_name:\"${escaped}\"`,
      ].join(" OR ");
      const params = new URLSearchParams({
        search,
        count: "patient.reaction.reactionmeddrapt.exact",
        limit: String(limit),
      });
      const response = await fetch(`https://api.fda.gov/drug/event.json?${params.toString()}`, { cache: "no-cache" });
      if (!response.ok) continue;
      const payload = await response.json();
      const reactions = Array.isArray(payload?.results)
        ? payload.results.slice(0, limit).map((row: { term?: string; count?: number }) => ({
            reaction: row.term,
            label: row.term,
            count: Number(row.count || 0),
          }))
        : [];
      if (!reactions.length) continue;
      const severe = new Set(["DEATH", "CARDIAC ARREST", "RESPIRATORY DEPRESSION", "COMA", "SEIZURE", "CONVULSION", "SEROTONIN SYNDROME"]);
      return {
        risk_kind: "signal",
        signal_id: `openfda_${item.id}_${term.toLowerCase().replace(/[^a-z0-9]+/g, "_")}`,
        substance_id: item.id,
        substance_name: displayName(item),
        query_term: term,
        reactions,
        risk_level: reactions.some((reaction: { reaction?: string }) => severe.has(String(reaction.reaction || "").toUpperCase())) ? "Moderate" : "Minor",
        confidence: "Low",
        source_tier: "Signal",
        interaction_type: "adverse_event_signal",
        source_name: "openFDA FAERS adverse event",
        source_url: "https://open.fda.gov/apis/drug/event/",
        note: `openFDA FAERS 自发不良事件报告中，${displayName(item)}（按 ${term} 检索）存在共报告事件。这是药物警戒候选信号，不代表因果关系、发生率或确认联用冲突。`,
      };
    }
    return null;
  }

  async localSeed() {
    const response = await fetch(`${this.localApiBase}/seed`, { cache: "no-cache" });
    if (!response.ok) throw new Error(`本地种子库不可用 HTTP ${response.status}`);
    return response.json() as Promise<LocalSeedPayload>;
  }

  async localSources() {
    const response = await fetch(`${this.localApiBase}/sources`, { cache: "no-cache" });
    if (!response.ok) throw new Error(`数据源状态不可用 HTTP ${response.status}`);
    return response.json();
  }

  async startLocalRebuild() {
    const response = await fetch(`${this.localApiBase}/rebuild`, { cache: "no-cache" });
    if (!response.ok) throw new Error(`启动重建失败 HTTP ${response.status}`);
    return response.json();
  }

  async localRebuildStatus() {
    const response = await fetch(`${this.localApiBase}/rebuild-status`, { cache: "no-cache" });
    if (!response.ok) throw new Error(`读取重建状态失败 HTTP ${response.status}`);
    return response.json();
  }

  async sourceUpdate(term: string, limit = 2) {
    const params = new URLSearchParams({ term, limit: String(limit) });
    const response = await fetch(`${this.localApiBase}/source-update?${params.toString()}`, { cache: "no-cache" });
    if (!response.ok) throw new Error(`同步公开源失败 HTTP ${response.status}`);
    return response.json();
  }

  async syncLocalDatabase(options: { shardKeys?: string[]; includeCommonShards?: boolean } = {}) {
    const manifest = await this.fetchJson<ApiManifest>("manifest.json", { refresh: true });
    const searchManifest = await this.fetchJson<SearchManifest>("search/manifest.json", { refresh: true });
    const common = options.includeCommonShards === false ? [] : ["ib", "wa", "ca", "se", "me", "pa", "am", "al", "co", "in"];
    const keys = [...new Set([...(options.shardKeys || []), ...common])].filter((key) => searchManifest.shards?.[key]);
    await Promise.all(keys.map((key) => this.fetchJson(`search/shards/${encodeURIComponent(key)}.json`, { refresh: true })));
    await saveStaticDbSyncState({
      lastSyncAt: Date.now(),
      source: this.apiBase,
      datasetVersion: manifest.dataset_version,
      manifests: 2,
      searchShards: keys.length,
    });
    this.searchManifest = searchManifest;
    this.shardCache.clear();
    return { manifest, searchManifest, shardKeys: keys };
  }

  private async fetchSearchShard(key: string, manifest?: SearchManifest) {
    if (this.shardCache.has(key)) return this.shardCache.get(key) || [];
    if (manifest?.shards && !manifest.shards[key]) {
      this.shardCache.set(key, []);
      return [];
    }
    const template = manifest?.shard_path || "search/shards/{key}.json";
    const rows = await this.safeFetch<SubstanceSummary>(template.replace("{key}", encodeURIComponent(key)));
    this.shardCache.set(key, rows);
    return rows;
  }

  private async safeFetch<T>(path?: string) {
    if (!path) return [] as T[];
    try {
      const payload = await this.fetchJson<T[] | T>(path);
      return Array.isArray(payload) ? payload : payload ? [payload] : [];
    } catch {
      return [];
    }
  }

  private async fetchJson<T>(path: string, options: { refresh?: boolean } = {}) {
    if (!path) throw new Error("缺少 API 路径");
    const cleanPath = path.replace(/^\/?api\//, "").replace(/^\//, "");
    if (!options.refresh) {
      const cached = await getCachedStaticJson<T>(cleanPath);
      if (cached) return cached;
    }
    const url = `${this.apiBase}/${cleanPath}`;
    try {
      const response = await fetch(url, { cache: cleanPath === "manifest.json" ? "no-store" : "no-cache" });
      if (!response.ok) throw new Error(`读取失败：${cleanPath} HTTP ${response.status}`);
      const payload = (await response.json()) as T;
      await cacheStaticJson(cleanPath, payload, this.apiBase);
      return payload;
    } catch (error) {
      const cached = await getCachedStaticJson<T>(cleanPath);
      if (cached) return cached;
      throw error;
    }
  }
}

function finitePositiveNumber(value: unknown) {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? numeric : undefined;
}

function firstPkNumber(row: PharmacokineticRow, fields: Array<keyof PharmacokineticRow>) {
  for (const field of fields) {
    const value = finitePositiveNumber(row[field]);
    if (value !== undefined) return value;
  }
  return undefined;
}

function mergePharmacokineticsIntoDetail(detail: SubstanceDetail, pharmacokinetics: PharmacokineticRow[]) {
  const rows = mergePkRows(
    normalizePkRows(detail.pharmacokinetics),
    normalizePkRows(detail.pharmacokinetics_detail),
    normalizePkRows(detail.remote_evidence?.pharmacokinetics),
    normalizePkRows(pharmacokinetics),
  );
  const halfLife = finitePositiveNumber(detail.base_half_life)
    ?? firstPkNumberFromRows(rows, ["half_life_hours", "half_life_hours_mean", "half_life_hours_upper"]);
  const onset = finitePositiveNumber(detail.base_onset) ?? firstPkNumberFromRows(rows, ["onset_minutes"]);
  const duration = finitePositiveNumber(detail.base_duration) ?? firstPkNumberFromRows(rows, ["duration_minutes"]);
  return {
    ...detail,
    base_half_life: halfLife ?? detail.base_half_life,
    base_onset: onset ?? detail.base_onset,
    base_duration: duration ?? detail.base_duration,
    pharmacokinetics: rows.length ? rows : detail.pharmacokinetics,
    remote_evidence: {
      ...(detail.remote_evidence || {}),
      pharmacokinetics: rows.length ? rows : detail.remote_evidence?.pharmacokinetics,
    },
  } satisfies SubstanceDetail;
}

function normalizePkRows(rows: unknown): PharmacokineticRow[] {
  if (!Array.isArray(rows)) return [];
  return rows.filter((row): row is PharmacokineticRow => Boolean(row && typeof row === "object"));
}

function mergePkRows(...groups: PharmacokineticRow[][]) {
  const rows: PharmacokineticRow[] = [];
  const seen = new Set<string>();
  for (const row of groups.flat()) {
    const key = [
      row.fact_id,
      row.source_name,
      row.standard_type,
      row.route,
      row.half_life_hours,
      row.half_life_hours_mean,
      row.half_life_hours_upper,
      row.onset_minutes,
      row.duration_minutes,
    ].map((part) => String(part ?? "")).join("|");
    if (seen.has(key)) continue;
    seen.add(key);
    rows.push(row);
  }
  return rows;
}

function firstPkNumberFromRows(rows: PharmacokineticRow[], fields: Array<keyof PharmacokineticRow>) {
  for (const row of rows) {
    const value = firstPkNumber(row, fields);
    if (value !== undefined) return value;
  }
  return undefined;
}
