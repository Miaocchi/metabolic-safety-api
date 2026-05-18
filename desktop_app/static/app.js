const state = {
  manifest: null,
  substances: [],
  substanceById: new Map(),
  journal: [],
  activeRisks: [],
  sources: [],
  remoteConfig: { enabled: false, baseUrl: "" },
  remoteManifest: null,
  remoteSearchIndex: null,
  remoteSubstanceCache: [],
  remoteInteractionCache: new Map(),
  remoteDoseRuleCache: new Map(),
  remoteOverdoseWarningCache: new Map(),
  remoteDrugEffectCache: new Map(),
  remotePharmacokineticCache: new Map(),
  remoteEnzymeRelationCache: new Map(),
  adverseSignalCache: new Map(),
  remoteImportToken: 0,
  remoteLastImportQuery: "",
  dataRequestToken: 0,
  riskRequestToken: 0,
  sourceRequestToken: 0,
  doseRules: [],
  curveZoom: 1,
  curvePanMinutes: 0,
  curveDrag: null,
  curveHoverRatio: null,
  curveHiddenSubstances: new Set(),
  advancedMode: false,
  themeMode: "system",
};

const colors = ["#00e676", "#2f80ff", "#ffd23f", "#ff1744", "#a855f7", "#00d4ff"];
const storageKey = "metabolic_safety_journal_v1";
const profileStorageKey = "metabolic_safety_profile_v1";
const curveZoomStorageKey = "metabolic_safety_curve_zoom_v1";
const curvePanStorageKey = "metabolic_safety_curve_pan_v1";
const uiModeStorageKey = "metabolic_safety_ui_mode_v1";
const themeModeStorageKey = "metabolic_safety_theme_mode_v1";
const remoteApiBaseStorageKey = "metabolic_safety_remote_api_base_v1";
const remoteFallbackStorageKey = "metabolic_safety_remote_fallback_v1";
const remoteSubstanceCacheStorageKey = "metabolic_safety_remote_substances_v1";
const remoteApiBaseMigratedStorageKey = "metabolic_safety_remote_api_base_migrated_v1";
const hostedRemoteApiBaseUrl = "https://miaocchi.github.io/metabolic-safety-api/api";
const defaultRemoteApiBaseUrl = "/remote-api";
const ethanolDensityGPerMl = 0.789;
const $ = (id) => document.getElementById(id);

const routeProfiles = {
  Oral: { label: "口服", ka: 1.0, f: 1.0, instant: false },
  Sublingual: { label: "舌下", ka: 1.8, f: 0.85, instant: true },
  Insufflated: { label: "鼻腔", ka: 2.2, f: 0.75, instant: true },
  Topical: { label: "经皮", ka: 0.25, f: 0.35, instant: false },
  IV: { label: "静脉/瞬时", ka: 999, f: 1.0, instant: true },
  Other: { label: "其他", ka: 1.0, f: 1.0, instant: false },
};

const stomachProfiles = {
  Fasting: { label: "完全空腹", ka: 1.5, f: 1.0 },
  Light: { label: "正常/少量进食", ka: 1.0, f: 1.0 },
  Heavy: { label: "高脂重餐", ka: 0.5, f: 1.08 },
};

const metabolicProfiles = {
  UM: { label: "\u8d85\u5feb\u4ee3\u8c22", activityScore: 2.75, ke: 1.45 },
  EM: { label: "\u6b63\u5e38\u4ee3\u8c22", activityScore: 1.75, ke: 1.0 },
  IM: { label: "\u4e2d\u95f4\u4ee3\u8c22", activityScore: 0.75, ke: 0.72 },
  PM: { label: "\u6162\u4ee3\u8c22", activityScore: 0.15, ke: 0.45 },
};

const hydrationProfiles = {
  Normal: { label: "\u6b63\u5e38\u6c34\u5408", vd: 1.0, renal: 1.0 },
  Dehydrated: { label: "\u8131\u6c34/\u4f53\u6db2\u4e0d\u8db3", vd: 0.88, renal: 0.92 },
  Overloaded: { label: "\u8865\u6db2/\u6c34\u80bf\u504f\u591a", vd: 1.18, renal: 0.98 },
};

const criticalStateProfiles = {
  Stable: { label: "\u7a33\u5b9a", cl: 1.0, vdHydrophilic: 1.0, renal: 1.0 },
  Infection: { label: "\u611f\u67d3/\u708e\u75c7", cl: 0.95, vdHydrophilic: 1.12, renal: 1.0 },
  Sepsis: { label: "\u91cd\u75c7\u611f\u67d3/\u6bdb\u7ec6\u8840\u7ba1\u6e17\u6f0f", cl: 0.85, vdHydrophilic: 1.35, renal: 0.9 },
  ARC: { label: "\u80be\u810f\u9ad8\u6e05\u9664 ARC", cl: 1.08, vdHydrophilic: 1.08, renal: 1.35 },
  CRRT: { label: "CRRT/\u4f53\u5916\u6e05\u9664", cl: 1.0, vdHydrophilic: 1.12, renal: 0.8 },
};
const doseSafetyRules = [];

const riskLevelLabels = {
  Contraindicated: "\u7981\u5fcc",
  Major: "\u4e25\u91cd",
  Moderate: "\u4e2d\u5ea6",
  Minor: "\u8f7b\u5fae",
  Dangerous: "\u5371\u9669",
  Unsafe: "\u4e0d\u5b89\u5168",
  Synergy: "\u534f\u540c/\u589e\u5f3a",
  "Low Risk": "\u4f4e\u98ce\u9669",
  NoKnownClinicalSignificance: "\u65e0\u660e\u786e\u4e34\u5e8a\u610f\u4e49",
  Unknown: "\u672a\u77e5",
};

const confidenceLabels = {
  High: "\u9ad8",
  Medium: "\u4e2d",
  Low: "\u4f4e",
  Unknown: "\u672a\u77e5",
};

const sourceTierLabels = {
  CuratedDB: "\u7b56\u5c55\u6570\u636e\u5e93",
  Regulatory: "\u76d1\u7ba1\u6807\u7b7e",
  Community: "\u793e\u533a\u6570\u636e",
  Signal: "\u5019\u9009\u4fe1\u53f7",
  Guideline: "\u6307\u5357",
  Literature: "\u6587\u732e/\u8bf4\u660e\u4e66",
  DoseRule: "\u5242\u91cf\u89c4\u5219",
  Unknown: "\u672a\u77e5\u6765\u6e90",
};

const interactionTypeLabels = {
  drug_interaction: "\u836f\u7269\u76f8\u4e92\u4f5c\u7528",
  dose_safety: "\u5242\u91cf\u5b89\u5168",
  pharmacokinetics: "\u836f\u4ee3\u52a8\u529b\u5b66",
  source_text: "\u6807\u7b7e\u539f\u6587",
  adverse_event_signal: "\u4e0d\u826f\u4e8b\u4ef6\u5019\u9009\u4fe1\u53f7",
};

const categoryLabels = {
  Drug: "\u836f\u7269",
  DrugLabel: "\u836f\u54c1\u6807\u7b7e",
  "RxNorm concept": "RxNorm \u6982\u5ff5",
  Stimulant: "\u5174\u594b\u5242",
  Depressant: "\u6291\u5236\u5242",
  Dissociative: "\u89e3\u79bb\u5242",
  Supplement: "\u8865\u5145\u5242",
  "Supplement/Food": "\u8865\u5145\u5242/\u98df\u7269",
  Food: "\u98df\u7269",
};

const uiModeProfiles = {
  toc: {
    key: "toc",
    label: "ToC \u4e2a\u4eba\u6a21\u5f0f",
    appTitle: "\u4e2a\u4eba\u4ee3\u8c22\u5b89\u5168\u65e5\u5fd7",
    settingsTitle: "\u4e2a\u4eba\u53c2\u6570",
    chartTitle: "\u4e2a\u4eba\u52a8\u6001\u66f2\u7ebf",
    riskTitle: "\u4e2a\u4eba\u98ce\u9669\u63d0\u793a",
    journalTitle: "\u672c\u5730\u65e5\u5fd7",
    modeTitle: "ToC \u4e2a\u4eba\u6a21\u5f0f",
    modeDesc: "\u4fdd\u7559\u5feb\u901f\u5f55\u5165\u3001\u5df2\u670d\u7528\u4f5c\u7528\u3001\u66f2\u7ebf\u548c\u53ef\u6267\u884c\u98ce\u9669\uff1b\u9690\u85cf\u6570\u636e\u6e90\u8fd0\u7ef4\u548c\u6a21\u578b\u660e\u7ec6\u3002",
    minVisibleRiskScore: 2,
    showUnknownRisks: false,
    maxRiskCards: 6,
  },
  tob: {
    key: "tob",
    label: "ToB \u63a7\u5236\u53f0",
    appTitle: "\u4ee3\u8c22\u5b89\u5168\u63a7\u5236\u53f0",
    settingsTitle: "\u6570\u636e\u6e90\u8bbe\u7f6e",
    chartTitle: "\u52a8\u6001\u4f30\u7b97\u66f2\u7ebf",
    riskTitle: "\u98ce\u9669\u63d0\u793a",
    journalTitle: "\u672c\u5730\u65e5\u5fd7",
    modeTitle: "ToB \u63a7\u5236\u53f0",
    modeDesc: "\u663e\u793a KPI\u3001\u6570\u636e\u6e90\u8fd0\u7ef4\u3001PMI\u3001\u5e93\u68c0\u7d22\u548c PopPK \u660e\u7ec6\uff0c\u7528\u4e8e\u6570\u636e\u7ba1\u7406\u4e0e\u9a8c\u8bc1\u3002",
    minVisibleRiskScore: 0,
    showUnknownRisks: true,
    maxRiskCards: 999,
  },
};

function modeProfile() {
  return state.advancedMode ? uiModeProfiles.tob : uiModeProfiles.toc;
}

function applyUiMode() {
  document.body.classList.toggle("advanced-mode", state.advancedMode);
  document.body.classList.toggle("basic-mode", !state.advancedMode);
  const mode = modeProfile();
  const bindings = {
    advancedModeState: mode.label,
    uiModePill: mode.label,
    appTitle: mode.appTitle,
    settingsTitle: mode.settingsTitle,
    modeTitle: mode.modeTitle,
    modeDesc: mode.modeDesc,
    chartTitle: mode.chartTitle,
    riskTitle: mode.riskTitle,
    journalTitle: mode.journalTitle,
  };
  Object.entries(bindings).forEach(([id, value]) => {
    const node = $(id);
    if (node) node.textContent = value;
  });
  const toggle = $("advancedModeToggle");
  if (toggle) toggle.checked = state.advancedMode;
  renderMeta();
  renderSelectedSubstanceInfo();
  renderJournal();
  renderRisks();
  if (state.advancedMode) {
    renderSources().catch(console.error);
    renderDataBrowser().catch(console.error);
  }
  requestAnimationFrame(drawCurve);
}

function loadUiMode() {
  state.advancedMode = localStorage.getItem(uiModeStorageKey) === "advanced";
  applyUiMode();
}

function setAdvancedMode(enabled) {
  state.advancedMode = Boolean(enabled);
  localStorage.setItem(uiModeStorageKey, state.advancedMode ? "advanced" : "basic");
  applyUiMode();
}

function applyThemeMode() {
  const mode = ["system", "light", "dark"].includes(state.themeMode) ? state.themeMode : "system";
  document.body.classList.toggle("theme-system", mode === "system");
  document.body.classList.toggle("theme-light", mode === "light");
  document.body.classList.toggle("theme-dark", mode === "dark");
  const select = $("themeModeSelect");
  if (select) select.value = mode;
  requestAnimationFrame(drawCurve);
}

function loadThemeMode() {
  state.themeMode = localStorage.getItem(themeModeStorageKey) || "system";
  applyThemeMode();
}

function setThemeMode(mode) {
  state.themeMode = ["system", "light", "dark"].includes(mode) ? mode : "system";
  localStorage.setItem(themeModeStorageKey, state.themeMode);
  applyThemeMode();
}

function normalizeRemoteBaseUrl(value) {
  let trimmed = String(value || "").trim();
  if (!trimmed) return "";
  trimmed = trimmed.replace(/[?#].*$/, "").replace(/\/+$/, "");
  if (!trimmed) return "";
  if (trimmed.startsWith("/remote-api")) return defaultRemoteApiBaseUrl;
  trimmed = trimmed.replace(/\/manifest\.json$/i, "");
  trimmed = trimmed.replace(/\/search\/index\.json$/i, "");
  trimmed = trimmed.replace(/\/search$/i, "");
  const apiMarker = "/metabolic-safety-api/api";
  const rootMarker = "/metabolic-safety-api";
  const apiIndex = trimmed.indexOf(apiMarker);
  if (apiIndex >= 0) return `${trimmed.slice(0, apiIndex)}${apiMarker}`;
  const rootIndex = trimmed.indexOf(rootMarker);
  if (rootIndex >= 0) return `${trimmed.slice(0, rootIndex)}${rootMarker}/api`;
  return trimmed || hostedRemoteApiBaseUrl;
}
function remoteEnabled() {
  return Boolean(state.remoteConfig?.enabled && state.remoteConfig?.baseUrl);
}

function remoteApiUrl(path) {
  const base = normalizeRemoteBaseUrl(state.remoteConfig?.baseUrl || "");
  if (!base) throw new Error("请先填写本机镜像或远程静态 API 地址。");
  return `${base}/${String(path || "").replace(/^\/+/, "")}`;
}

async function fetchRemoteJson(path, options = {}) {
  const url = remoteApiUrl(path);
  const response = await fetch(url, { cache: options.cache || "force-cache" });
  if (!response.ok) {
    if (response.status === 404 && options.optional) return options.fallback ?? null;
    throw new Error(`远程源请求失败：HTTP ${response.status} · ${url}`);
  }
  return response.json();
}

function setRemoteApiStatus(message, kind = "") {
  const target = $("remoteApiStatus");
  if (!target) return;
  target.className = `remote-api-status ${kind}`.trim();
  target.textContent = message;
}

function loadRemoteConfig() {
  const storedBase = localStorage.getItem(remoteApiBaseStorageKey) || "";
  const baseUrl = storedBase ? normalizeRemoteBaseUrl(storedBase) : hostedRemoteApiBaseUrl;
  if (!storedBase) localStorage.setItem(remoteApiBaseStorageKey, baseUrl);
  state.remoteConfig = {
    enabled: localStorage.getItem(remoteFallbackStorageKey) === "1",
    baseUrl,
  };
  try {
    const cached = JSON.parse(localStorage.getItem(remoteSubstanceCacheStorageKey) || "[]");
    state.remoteSubstanceCache = Array.isArray(cached) ? cached : [];
  } catch {
    state.remoteSubstanceCache = [];
  }
  mergeRemoteCachedSubstances();
  syncRemoteControls();
}

function syncRemoteControls() {
  const input = $("remoteApiBase");
  const enabled = $("remoteFallbackEnabled");
  if (input) input.value = state.remoteConfig.baseUrl || "";
  if (enabled) enabled.checked = Boolean(state.remoteConfig.enabled);
  const base = state.remoteConfig.baseUrl;
  if (!base) {
    setRemoteApiStatus("\u8fdc\u7a0b\u56de\u9000\u9ed8\u8ba4\u5173\u95ed\uff1b\u9ed8\u8ba4\u4f7f\u7528 GitHub Pages \u65b0\u7248 /api\uff0c\u4e5f\u53ef\u586b\u5199\u672c\u673a\u955c\u50cf /remote-api\u3002", "");
  } else if (state.remoteConfig.enabled) {
    setRemoteApiStatus(`\u8fdc\u7a0b\u56de\u9000\u5df2\u542f\u7528\uff1a${base}`, "ok");
  } else {
    setRemoteApiStatus(`\u8fdc\u7a0b\u6e90\u5df2\u4fdd\u5b58\u4f46\u672a\u542f\u7528\uff1a${base}`, "");
  }
}

function saveRemoteConfigFromControls() {
  const base = normalizeRemoteBaseUrl($("remoteApiBase")?.value || "");
  const enabled = Boolean($("remoteFallbackEnabled")?.checked);
  state.remoteConfig = { baseUrl: base, enabled };
  state.remoteManifest = null;
  state.remoteSearchIndex = null;
  state.remoteInteractionCache = new Map();
  state.remoteDoseRuleCache = new Map();
  state.remoteOverdoseWarningCache = new Map();
  state.remoteDrugEffectCache = new Map();
  state.remotePharmacokineticCache = new Map();
  state.remoteEnzymeRelationCache = new Map();
  localStorage.setItem(remoteApiBaseStorageKey, base);
  localStorage.setItem(remoteFallbackStorageKey, enabled ? "1" : "0");
  syncRemoteControls();
}

function saveRemoteSubstanceCache() {
  const byId = new Map();
  for (const item of state.remoteSubstanceCache || []) {
    if (item?.id) byId.set(item.id, item);
  }
  state.remoteSubstanceCache = [...byId.values()].sort((a, b) => String(a.id).localeCompare(String(b.id)));
  localStorage.setItem(remoteSubstanceCacheStorageKey, JSON.stringify(state.remoteSubstanceCache.slice(0, 300)));
}

function normalizeRemoteSubstance(substance = {}) {
  const identifiers = substance.identifiers || {};
  const aliases = Array.isArray(substance.aliases) ? substance.aliases.join(", ") : (substance.aliases || identifiers.aliases || "");
  return {
    ...substance,
    identifiers: { ...identifiers, aliases },
    remote_source: substance.remote_source || "remote_static_api",
  };
}

function mergeRemoteSubstance(substance = {}, persist = true) {
  if (!substance?.id) return false;
  const normalized = normalizeRemoteSubstance(substance);
  const existing = state.substanceById.get(normalized.id);
  if (existing) {
    state.substanceById.set(normalized.id, { ...existing, ...normalized, identifiers: { ...(existing.identifiers || {}), ...(normalized.identifiers || {}) } });
    state.substances = state.substances.map((item) => item.id === normalized.id ? state.substanceById.get(normalized.id) : item);
  } else {
    state.substanceById.set(normalized.id, normalized);
    state.substances.push(normalized);
    state.substances.sort((a, b) => (a.name_zh || a.name_en || a.id).localeCompare(b.name_zh || b.name_en || b.id, "zh-CN"));
  }
  if (persist) {
    const cacheById = new Map((state.remoteSubstanceCache || []).map((item) => [item.id, item]));
    cacheById.set(normalized.id, normalized);
    state.remoteSubstanceCache = [...cacheById.values()];
    saveRemoteSubstanceCache();
  }
  return !existing;
}

function mergeRemoteCachedSubstances() {
  for (const item of state.remoteSubstanceCache || []) {
    mergeRemoteSubstance(item, false);
  }
}

async function ensureRemoteManifest() {
  if (!remoteEnabled()) return null;
  if (!state.remoteManifest) state.remoteManifest = await fetchRemoteJson("manifest.json", { cache: "no-cache" });
  return state.remoteManifest;
}

async function ensureRemoteSearchIndex() {
  if (!remoteEnabled()) return [];
  if (!state.remoteSearchIndex) {
    await ensureRemoteManifest();
    state.remoteSearchIndex = await fetchRemoteJson("search/index.json");
  }
  return Array.isArray(state.remoteSearchIndex) ? state.remoteSearchIndex : [];
}

function remoteSearchTerms(item = {}) {
  const aliases = Array.isArray(item.aliases) ? item.aliases : String(item.aliases || "").split(/[|,]/);
  return [item.id, item.name_en, item.name_zh, ...aliases]
    .filter(Boolean)
    .map((value) => String(value).trim().toLowerCase())
    .filter(Boolean);
}

function remoteSearchHaystack(item = {}) {
  return remoteSearchTerms(item).join(" ");
}

function remoteSearchScore(item = {}, normalized = "") {
  const terms = remoteSearchTerms(item);
  if (!terms.length) return 0;
  if (terms.some((term) => term === normalized)) return 100;
  if (terms.some((term) => term.startsWith(normalized))) return 80;
  const id = String(item.id || "").toLowerCase();
  if (id.includes(normalized)) return 62;
  if (terms.some((term) => term.includes(normalized))) return 42;
  return remoteSearchHaystack(item).includes(normalized) ? 20 : 0;
}

async function searchRemoteSubstances(query, limit = 30) {
  const normalized = String(query || "").trim().toLowerCase();
  if (!normalized || !remoteEnabled()) return [];
  const index = await ensureRemoteSearchIndex();
  return index
    .map((item) => ({ item, score: remoteSearchScore(item, normalized) }))
    .filter((row) => row.score > 0)
    .sort((a, b) => b.score - a.score || String(a.item.name_zh || a.item.name_en || a.item.id).length - String(b.item.name_zh || b.item.name_en || b.item.id).length)
    .slice(0, limit)
    .map((row) => row.item);
}
async function remotePathsForId(id) {
  if (!id || !remoteEnabled()) return {};
  const index = await ensureRemoteSearchIndex();
  const item = index.find((row) => row.id === id);
  return item?.paths || {
    substance: `substances/by-id/${encodeURIComponent(id)}.json`,
    interactions: `interactions/by-substance/${encodeURIComponent(id)}.json`,
    dose_rules: `dose-rules/by-substance/${encodeURIComponent(id)}.json`,
    dose_candidates: `dose-candidates/by-substance/${encodeURIComponent(id)}.json`,
    overdose_warnings: `overdose-warnings/by-substance/${encodeURIComponent(id)}.json`,
    drug_effects: `drug-effects/by-substance/${encodeURIComponent(id)}.json`,
    pharmacokinetics: `pharmacokinetics/by-substance/${encodeURIComponent(id)}.json`,
    enzyme_relations: `enzyme-relations/by-substance/${encodeURIComponent(id)}.json`,
  };
}

async function fetchRemoteEvidenceRows(id, pathKey, cache, limit = 24, explicitPaths = null) {
  if (!id || !remoteEnabled()) return [];
  if (cache.has(id)) return cache.get(id);
  try {
    const paths = explicitPaths || await remotePathsForId(id);
    const path = paths?.[pathKey];
    if (!path) {
      cache.set(id, []);
      return [];
    }
    const rows = await fetchRemoteJson(path, { optional: true, fallback: [] });
    const list = normalizeRemoteList(rows).slice(0, limit);
    cache.set(id, list);
    return list;
  } catch {
    cache.set(id, []);
    return [];
  }
}

function mergeRemoteEvidenceIntoSubstance(substance = {}, evidence = {}) {
  const remoteEvidence = {
    ...(substance.remote_evidence || {}),
    drug_effects: normalizeRemoteList(evidence.drug_effects || substance.remote_evidence?.drug_effects || []),
    pharmacokinetics: normalizeRemoteList(evidence.pharmacokinetics || substance.remote_evidence?.pharmacokinetics || []),
    enzyme_relations: normalizeRemoteList(evidence.enzyme_relations || substance.remote_evidence?.enzyme_relations || []),
  };
  const enzymeTags = remoteEvidence.enzyme_relations.map((row) => row.tag).filter(Boolean);
  const cypTags = [...new Set([...(substance.cyp_tags || []), ...enzymeTags])];
  const pkHalfLife = remoteEvidence.pharmacokinetics.find((row) => row.half_life_hours !== null && row.half_life_hours !== undefined)?.half_life_hours;
  return {
    ...substance,
    cyp_tags: cypTags,
    base_half_life: substance.base_half_life || pkHalfLife || undefined,
    remote_evidence: remoteEvidence,
  };
}

async function fetchRemoteSubstanceDetail(id) {
  if (!id || !remoteEnabled()) return null;
  const paths = await remotePathsForId(id);
  const detail = normalizeRemoteSubstance(await fetchRemoteJson(paths.substance));
  const detailPaths = { ...paths, ...(detail.paths || {}) };
  const [drugEffects, pharmacokinetics, enzymeRelations] = await Promise.all([
    fetchRemoteEvidenceRows(id, "drug_effects", state.remoteDrugEffectCache, 24, detailPaths),
    fetchRemoteEvidenceRows(id, "pharmacokinetics", state.remotePharmacokineticCache, 16, detailPaths),
    fetchRemoteEvidenceRows(id, "enzyme_relations", state.remoteEnzymeRelationCache, 24, detailPaths),
  ]);
  return normalizeRemoteSubstance(mergeRemoteEvidenceIntoSubstance(detail, {
    drug_effects: drugEffects,
    pharmacokinetics,
    enzyme_relations: enzymeRelations,
  }));
}

async function fetchRemoteDoseRulesForId(id) {
  if (!id || !remoteEnabled()) return [];
  if (state.remoteDoseRuleCache.has(id)) return state.remoteDoseRuleCache.get(id);
  try {
    const paths = await remotePathsForId(id);
    const rows = await fetchRemoteJson(paths.dose_rules, { optional: true, fallback: [] });
    const list = normalizeRemoteList(rows);
    state.remoteDoseRuleCache.set(id, list);
    return list;
  } catch {
    state.remoteDoseRuleCache.set(id, []);
    return [];
  }
}


function normalizeRemoteList(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.items)) return payload.items;
  if (payload && typeof payload === "object") return [payload];
  return [];
}

async function fetchRemoteDoseRulesForIds(ids = []) {
  if (!remoteEnabled() || !ids.length) return [];
  const rows = (await Promise.all([...new Set(ids)].map((id) => fetchRemoteDoseRulesForId(id)))).flat();
  mergeRemoteDoseRules(rows);
  return rows;
}

async function fetchRemoteOverdoseWarningsForId(id) {
  return fetchRemoteEvidenceRows(id, "overdose_warnings", state.remoteOverdoseWarningCache, 6);
}


function doseRuleSubjectKey(rule = {}) {
  return String(rule.subject_id || rule.key || rule.original_subject_id || "").toLowerCase();
}

function doseRuleRouteKey(rule = {}) {
  return String(rule.route || "").trim().toLowerCase();
}

function doseRuleIsReviewed(rule = {}) {
  return rule.review_status === "machine_checked" || (rule.confidence === "High" && !rule.population?.review_required);
}

function doseRuleNeedsReview(rule = {}) {
  const normalizedFrom = Array.isArray(rule.normalized_from) ? rule.normalized_from : [];
  return rule.review_status === "unreviewed" || Boolean(rule.population?.review_required) || normalizedFrom.includes("dose_candidate");
}

function shouldSkipRemoteDoseRule(rule = {}, existingRules = []) {
  if (!doseRuleNeedsReview(rule)) return false;
  const subject = doseRuleSubjectKey(rule);
  if (!subject) return false;
  const route = doseRuleRouteKey(rule);
  return existingRules.some((existing) => {
    if (!doseRuleIsReviewed(existing)) return false;
    if (doseRuleSubjectKey(existing) !== subject) return false;
    const existingRoute = doseRuleRouteKey(existing);
    return !route || !existingRoute || route === existingRoute;
  });
}

function mergeRemoteDoseRules(rules = []) {
  const incoming = normalizeRemoteList(rules);
  if (!incoming.length) return;
  const byId = new Map((state.doseRules || []).map((rule) => [rule.rule_id, rule]));
  const existingRules = [...byId.values()];
  const sortedRules = [...incoming].sort((a, b) => Number(doseRuleIsReviewed(b)) - Number(doseRuleIsReviewed(a)));
  for (const rule of sortedRules) {
    if (!rule?.rule_id) continue;
    if (shouldSkipRemoteDoseRule(rule, existingRules)) continue;
    const normalized = { ...rule, remote_source: rule.remote_source || "remote_static_api" };
    byId.set(rule.rule_id, normalized);
    existingRules.push(normalized);
  }
  state.doseRules = [...byId.values()];
}

async function addRemoteSubstanceById(id) {
  const detail = await fetchRemoteSubstanceDetail(id);
  if (!detail) throw new Error("\u8fdc\u7a0b\u7269\u8d28\u8be6\u60c5\u4e0d\u5b58\u5728\u3002");
  mergeRemoteSubstance(detail, true);
  mergeRemoteDoseRules(await fetchRemoteDoseRulesForId(id));
  return detail;
}

async function fetchRemoteInteractionsForId(id) {
  if (!id || !remoteEnabled()) return [];
  if (state.remoteInteractionCache.has(id)) return state.remoteInteractionCache.get(id);
  try {
    const paths = await remotePathsForId(id);
    const rows = await fetchRemoteJson(paths.interactions, { optional: true, fallback: [] });
    const list = normalizeRemoteList(rows);
    state.remoteInteractionCache.set(id, list);
    return list;
  } catch {
    state.remoteInteractionCache.set(id, []);
    return [];
  }
}

async function fetchRemoteInteractionsForIds(ids) {
  if (!remoteEnabled() || !ids?.length) return [];
  const active = new Set(ids);
  const rows = (await Promise.all(ids.map((id) => fetchRemoteInteractionsForId(id)))).flat();
  const byId = new Map();
  for (const row of rows) {
    if (!active.has(row.substance_a_id) || !active.has(row.substance_b_id)) continue;
    byId.set(row.interaction_id || `${row.substance_a_id}_${row.substance_b_id}_${row.risk_level}`, { ...row, remote_source: "remote_static_api" });
  }
  return [...byId.values()];
}

async function fetchAdverseSignalsForIds(ids) {
  const cleanIds = [...new Set((ids || []).filter(Boolean))].sort();
  if (!cleanIds.length) return [];
  const key = cleanIds.join(",");
  const cached = state.adverseSignalCache.get(key);
  if (cached && Date.now() - cached.ts < 6 * 60 * 60 * 1000) return cached.items;
  try {
    const response = await fetch(`/api/adverse-signals?ids=${encodeURIComponent(key)}&limit=3`, { cache: "no-cache" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    const items = Array.isArray(payload.items) ? payload.items : [];
    state.adverseSignalCache.set(key, { ts: Date.now(), items });
    return items;
  } catch {
    state.adverseSignalCache.set(key, { ts: Date.now(), items: [] });
    return [];
  }
}

async function testRemoteApiConnection() {
  saveRemoteConfigFromControls();
  if (!state.remoteConfig.baseUrl) {
    setRemoteApiStatus("\u8bf7\u5148\u586b\u5199 本机镜像 /remote-api 或 GitHub Pages /api \u5730\u5740\u3002", "error");
    return;
  }
  try {
    const manifest = await fetchRemoteJson("manifest.json", { cache: "no-cache" });
    if (!manifest || typeof manifest !== "object") throw new Error("\u8fdc\u7a0b\u6e90 manifest.json \u683c\u5f0f\u4e0d\u6b63\u786e\u3002");
    state.remoteManifest = manifest;
    const counts = manifest.counts || {};
    const version = manifest.api_version || "static API";
    const enabledNote = state.remoteConfig.enabled ? "\u5df2\u542f\u7528" : "\u672a\u542f\u7528\uff0c\u4ec5\u5b8c\u6210\u8fde\u63a5\u6d4b\u8bd5";
    setRemoteApiStatus(`\u8fde\u63a5\u6210\u529f\uff1a${version} \u00b7 ${formatNumber(counts.substances || 0, 0)} \u4e2a\u7269\u8d28 \u00b7 ${formatNumber(counts.interactions || 0, 0)} \u6761\u76f8\u4e92\u4f5c\u7528 \u00b7 ${formatNumber(counts.dose_rules || 0, 0)} \u6761\u5242\u91cf\u89c4\u5219 \u00b7 ${formatNumber(counts.dose_candidates || 0, 0)} \u6761\u5242\u91cf\u5019\u9009 \u00b7 ${formatNumber(counts.overdose_warnings || 0, 0)} \u6761\u8fc7\u91cf\u8b66\u544a \u00b7 ${enabledNote}`, "ok");
  } catch (error) {
    setRemoteApiStatus(error.message || String(error), "error");
  }
}

async function scheduleRemoteSubstanceImport(query) {
  if (!remoteEnabled()) return;
  const normalized = String(query || "").trim();
  if (!normalized || normalized.length < 2) return;
  const token = ++state.remoteImportToken;
  state.remoteLastImportQuery = normalized;
  await sleep(260);
  if (token !== state.remoteImportToken || state.remoteLastImportQuery !== normalized) return;
  try {
    const matches = await searchRemoteSubstances(normalized, 8);
    let changed = 0;
    for (const match of matches.slice(0, 8)) {
      const existing = state.substanceById.get(match.id);
      const hasRemoteEffects = normalizeRemoteList(existing?.remote_evidence?.drug_effects).length > 0;
      const hasRemotePk = normalizeRemoteList(existing?.remote_evidence?.pharmacokinetics).length > 0;
      const hasRemoteEnzymes = normalizeRemoteList(existing?.remote_evidence?.enzyme_relations).length > 0;
      if (existing && hasRemoteEffects && hasRemotePk && hasRemoteEnzymes) continue;
      const detail = await addRemoteSubstanceById(match.id);
      if (detail) changed += 1;
    }
    if (changed && ($("substanceFilter")?.value || "").trim() === normalized) renderSubstanceOptions();
    if (changed) renderSelectedSubstanceInfo();
  } catch (error) {
    setRemoteApiStatus(`\u8fdc\u7a0b\u68c0\u7d22\u5931\u8d25\uff1a${error.message || error}`, "error");
  }
}

function updateKpis() {
  const active = activeEntries().length;
  const risks = state.activeRisks?.length || 0;
  const journal = state.journal?.length || 0;
  const sources = state.sources?.length || 0;
  if ($("activeKpi")) $("activeKpi").textContent = String(active);
  if ($("riskKpi")) $("riskKpi").textContent = String(risks);
  if ($("journalKpi")) $("journalKpi").textContent = String(journal);
  if ($("sourceKpi")) $("sourceKpi").textContent = String(sources);
}

function renderPmi() {
  const target = $("pmiSummary");
  const meta = $("pmiScoreMeta");
  if (!target) return;
  const entries = activeEntries();
  if (!entries.length) {
    target.className = "pmi-summary empty";
    target.textContent = "\u6682\u65e0\u6d3b\u8dc3\u6444\u5165\uff0c\u4fdd\u5b58\u65e5\u5fd7\u540e\u751f\u6210 PMI\u3002";
    if (meta) meta.textContent = "\u7b49\u5f85\u6a21\u578b\u8ba1\u7b97";
    return;
  }
  const now = Date.now();
  const riskScore = Math.min(40, (state.activeRisks || []).reduce((sum, risk) => sum + Math.max(0, riskSortValue(risk.risk_level)), 0) * 6);
  let exposureScore = 0;
  let modifierScore = 0;
  let totalExposure = 0;
  const rows = entries.map((entry) => {
    const substance = state.substanceById.get(entry.substanceId) || { id: entry.substanceId };
    const params = adjustedPkParams(entry, substance);
    const elapsedHours = minutesBetween(entry.timestamp, now) / 60;
    const exposure = elapsedHours < 0 ? 0 : concentrationAt(elapsedHours, Number(entry.dosage || 0), params);
    const metrics = exposureMetricsForEntry(entry, params);
    totalExposure += exposure;
    exposureScore += Math.min(16, exposure > 0 ? Math.log10(exposure + 1) * 7 : 0);
    modifierScore += Math.max(0, (params.profile.sleepDebtHours || 0) * 0.8);
    modifierScore += params.profile.coreTempC >= 39 ? 7 : params.profile.coreTempC >= 37.8 ? 4 : 0;
    modifierScore += Math.max(0, (params.adjustedHalfLifeHours / Math.max(params.baseHalfLifeHours || 1, 1) - 1) * 8);
    return {
      name: substanceName(entry.substanceId),
      exposure,
      cmax: metrics.cmax,
      halfLife: params.adjustedHalfLifeHours,
      warnings: params.warnings || [],
    };
  }).sort((a, b) => b.exposure - a.exposure);
  const pmi = Math.max(0, Math.min(100, Math.round(18 + riskScore + exposureScore + modifierScore)));
  const level = pmi >= 75 ? "\u9ad8\u8d1f\u8377" : pmi >= 50 ? "\u4e2d\u8d1f\u8377" : "\u4f4e\u8d1f\u8377";
  target.className = `pmi-summary level-${pmi >= 75 ? "high" : pmi >= 50 ? "medium" : "low"}`;
  if (meta) meta.textContent = `${pmi}/100 \u00b7 ${level}`;
  const topRows = rows.slice(0, 4).map((row) => `
    <div class="pmi-row">
      <span>${escapeHtml(row.name)}</span>
      <strong>${formatNumber(row.exposure, 3)}</strong>
      <small>t1/2 ${row.halfLife.toFixed(1)}h \u00b7 Cmax ${formatNumber(row.cmax, 3)}</small>
    </div>`).join("");
  const warningCount = rows.reduce((sum, row) => sum + row.warnings.length, 0);
  const forwardRows = forwardExposureGroups(entries, now, 24).slice(0, state.advancedMode ? 5 : 3);
  const forwardIndex = forwardRows.length ? Math.min(100, Math.round(forwardRows.reduce((sum, row) => sum + row.index, 0) / Math.sqrt(forwardRows.length))) : 0;
  target.innerHTML = `
    <div class="pmi-gauge">
      <div class="pmi-score">${pmi}</div>
      <div><strong>${level}</strong><span>\u603b\u66b4\u9732 ${formatNumber(totalExposure, 3)} \u00b7 \u5411\u540e\u66b4\u9732\u6307\u6570 ${forwardIndex}/100 \u00b7 \u6d3b\u8dc3 ${entries.length} \u9879</span></div>
    </div>
    <div class="pmi-bars">
      <div><span>\u51b2\u7a81/\u8fc7\u91cf</span><strong>${Math.round(riskScore)}</strong></div>
      <div><span>\u6a21\u578b\u66b4\u9732</span><strong>${Math.round(exposureScore)}</strong></div>
      <div><span>\u4e2a\u4f53\u4fee\u6b63</span><strong>${Math.round(modifierScore)}</strong></div>
      <div><span>\u5411\u540e\u66b4\u9732</span><strong>${forwardIndex}</strong></div>
    </div>
    <div class="pmi-table">${topRows}</div>
    <div class="pmi-forward">
      <div class="pmi-forward-head"><strong>\u5411\u540e\u66b4\u9732\u6307\u6570</strong><span>\u672a\u6765 24h AUC / \u5cf0\u503c / \u8fbe\u5cf0\u65f6\u95f4</span></div>
      <div class="pmi-forward-list">${renderForwardExposureRows(forwardRows)}</div>
    </div>
  `;
}


function concentrationUnitLabel(entry = {}) {
  const unit = String(entry?.unit || "mg").toLowerCase();
  if (unit === "mcg") return "ug";
  return unit || "mg";
}


function forwardExposureMetricsForEntry(entry, params, now = Date.now(), horizonHours = 24) {
  const dose = Number(entry.dosage || 0);
  if (!Number.isFinite(dose) || dose <= 0) return null;
  const elapsedHours = minutesBetween(entry.timestamp, now) / 60;
  const samples = 96;
  const stepHours = horizonHours / samples;
  let previous = concentrationAt(elapsedHours, dose, params);
  let auc24 = 0;
  let peak = previous;
  let tPeak = 0;
  for (let i = 1; i <= samples; i += 1) {
    const offsetHours = stepHours * i;
    const value = concentrationAt(elapsedHours + offsetHours, dose, params);
    auc24 += ((previous + value) / 2) * stepHours;
    if (value > peak) {
      peak = value;
      tPeak = offsetHours;
    }
    previous = value;
  }
  return {
    current: concentrationAt(elapsedHours, dose, params),
    auc24,
    peak,
    minutesToPeak: tPeak * 60,
    halfLifeHours: params.adjustedHalfLifeHours || 0,
    unit: concentrationUnitLabel(entry),
  };
}

function forwardExposureIndex(auc24, peak, minutesToPeak, halfLifeHours) {
  const aucScore = Math.min(62, Math.log10(Math.max(auc24, 0) + 1) * 30);
  const peakScore = Math.min(26, Math.log10(Math.max(peak, 0) + 1) * 16);
  const peakSoonScore = minutesToPeak > 0 && minutesToPeak <= 180 ? 8 : 0;
  const lingerScore = Math.min(12, Math.max(0, Number(halfLifeHours || 0) - 6) * 0.8);
  return Math.round(clampNumber(aucScore + peakScore + peakSoonScore + lingerScore, 0, 0, 100));
}

function forwardExposureGroups(entries = activeEntries(), now = Date.now(), horizonHours = 24) {
  const bySubstance = new Map();
  entries.forEach((entry) => {
    const substance = state.substanceById.get(entry.substanceId) || { id: entry.substanceId };
    const params = adjustedPkParams(entry, substance);
    const metrics = forwardExposureMetricsForEntry(entry, params, now, horizonHours);
    if (!metrics) return;
    const group = bySubstance.get(entry.substanceId) || {
      id: entry.substanceId,
      name: substanceName(entry.substanceId),
      auc24: 0,
      current: 0,
      peak: 0,
      minutesToPeak: null,
      halfLifeHours: 0,
      count: 0,
      unitSet: new Set(),
    };
    group.auc24 += metrics.auc24;
    group.current += metrics.current;
    group.peak = Math.max(group.peak, metrics.peak);
    if (metrics.minutesToPeak > 0) {
      group.minutesToPeak = group.minutesToPeak === null ? metrics.minutesToPeak : Math.min(group.minutesToPeak, metrics.minutesToPeak);
    }
    group.halfLifeHours = Math.max(group.halfLifeHours, metrics.halfLifeHours);
    group.count += 1;
    group.unitSet.add(metrics.unit);
    bySubstance.set(entry.substanceId, group);
  });
  return [...bySubstance.values()].map((group) => {
    const unit = group.unitSet.size === 1 ? [...group.unitSet][0] : "mixed";
    const minutesToPeak = group.minutesToPeak ?? 0;
    return {
      ...group,
      unit,
      minutesToPeak,
      index: forwardExposureIndex(group.auc24, group.peak, minutesToPeak, group.halfLifeHours),
    };
  }).sort((a, b) => b.index - a.index || b.auc24 - a.auc24);
}

function forwardExposureUnitText(unit) {
  return unit === "mixed" ? "mixed/L" : `${unit}/L`;
}

function renderForwardExposureRows(rows = []) {
  if (!rows.length) return `<div class="pmi-forward-empty">\u672a\u68c0\u51fa\u672a\u6765 24h \u7684\u660e\u663e\u5269\u4f59\u66b4\u9732\u3002</div>`;
  return rows.map((row) => {
    const unitText = forwardExposureUnitText(row.unit);
    const peakTime = row.minutesToPeak > 0 ? `${formatDurationMinutes(row.minutesToPeak)}\u540e\u8fbe\u5cf0` : "\u5df2\u5728\u9ad8\u4f4d/\u5df2\u8fc7\u5cf0";
    const doseCount = `\u00d7${row.count}`;
    return `
      <div class="pmi-forward-row">
        <div class="pmi-forward-drug"><span>${escapeHtml(row.name)}</span></div>
        <div class="pmi-forward-count"><span>${escapeHtml(doseCount)}</span></div>
        <div class="pmi-forward-peak"><small>${escapeHtml(peakTime)}</small></div>
        <strong>${row.index}</strong>
        <small>AUC24 ${formatNumber(row.auc24, row.auc24 < 1 ? 3 : 1)} \u00b7 peak ${formatNumber(row.peak, row.peak < 1 ? 3 : 2)} ${escapeHtml(unitText)}</small>
      </div>
    `;
  }).join("");
}
function exposureForecasts(entries = activeEntries(), now = Date.now()) {
  const forecasts = [];
  entries.forEach((entry) => {
    if (!entry.timestamp) return;
    const substance = state.substanceById.get(entry.substanceId) || { id: entry.substanceId };
    const params = adjustedPkParams(entry, substance);
    const dose = Number(entry.dosage || 0);
    if (!Number.isFinite(dose) || dose <= 0) return;
    const elapsedHours = minutesBetween(entry.timestamp, now) / 60;
    const horizonHours = Math.min(72, Math.max(12, (params.adjustedHalfLifeHours || 4) * 3 + (params.tlagHours || 0) + 6));
    const metrics = exposureMetricsForEntry(entry, params, horizonHours);
    if (!Number.isFinite(metrics.cmax) || metrics.cmax <= 0) return;
    const minutesToPeak = (metrics.tmaxHours - elapsedHours) * 60;
    if (minutesToPeak <= 8 || minutesToPeak > 12 * 60) return;
    const current = elapsedHours >= 0 ? concentrationAt(elapsedHours, dose, params) : 0;
    const lift = metrics.cmax - current;
    if (lift < Math.max(metrics.cmax * 0.12, 0.000001)) return;
    const effect = compactSubstanceEffect(substance);
    forecasts.push({
      entry,
      substance,
      name: substanceName(entry.substanceId),
      effect,
      current,
      peak: metrics.cmax,
      minutesToPeak,
      elapsedHours,
      unit: concentrationUnitLabel(entry),
      tmaxHours: metrics.tmaxHours,
    });
  });
  return forecasts.sort((a, b) => a.minutesToPeak - b.minutesToPeak || b.peak - a.peak);
}

function exposureForecastLine(forecast) {
  const digits = forecast.peak < 1 ? 3 : forecast.peak < 10 ? 2 : 1;
  const currentText = formatNumber(forecast.current, digits);
  const peakText = formatNumber(forecast.peak, digits);
  const startText = forecast.elapsedHours < 0
    ? `\u8ddd\u5f00\u59cb ${formatDurationMinutes(Math.abs(forecast.elapsedHours * 60))}\uff1b`
    : "";
  return `\u9884\u8b66\uff1a${forecast.name}${startText}\u9884\u8ba1 ${formatDurationMinutes(forecast.minutesToPeak)} \u540e\u63a5\u8fd1\u5cf0\u503c\uff08${currentText} \u2192 ${peakText} ${forecast.unit}/L\uff09\uff0c${forecast.effect}\u76f8\u5173\u526f\u4f5c\u7528\u53ef\u80fd\u5728\u8fbe\u5cf0\u524d\u540e\u66f4\u660e\u663e\u3002`;
}

function compactWarningNote(note = "") {
  const cleaned = String(note || "")
    .replace(/\u8fd9\u662f\u672c\u5730\u5242\u91cf\u89c4\u5219\u63d0\u793a\uff0c\u4e0d\u66ff\u4ee3\u533b\u751f\u3001\u836f\u5e08\u6216\u6025\u6551\u5224\u65ad\u3002?/g, "")
    .replace(/\u8fd9\u662f\u836f\u7269\u8b66\u6212\u5019\u9009\u4fe1\u53f7\uff0c\u4e0d\u4ee3\u8868\u56e0\u679c\u5173\u7cfb\u3001\u53d1\u751f\u7387\u6216\u5df2\u786e\u8ba4\u8054\u7528\u51b2\u7a81\uff1b\u7528\u4e8e\u63d0\u9192\u8bb0\u5f55\u75c7\u72b6\u5e76\u5fc5\u8981\u65f6\u54a8\u8be2\u533b\u751f\/\u836f\u5e08\u3002?/g, "\u5019\u9009\u4fe1\u53f7\uff0c\u975e\u56e0\u679c\u8bc1\u636e\u3002")
    .replace(/\s+/g, " ")
    .trim();
  return cleaned || "\u9700\u8981\u7ed3\u5408\u5242\u91cf\u3001\u65f6\u95f4\u548c\u5f53\u524d\u72b6\u6001\u7ee7\u7eed\u89c2\u5bdf\u3002";
}

function splitWarningNote(note = "") {
  const text = compactWarningNote(note);
  const boundaryLabels = "(?:\u6765\u6e90\u5c42\u7ea7|\u6570\u636e\u6765\u6e90|\u53ef\u4fe1\u5ea6|\u7c7b\u578b|\u5f53\u524d|\u6700\u5927|\u5355\u6b21|\u7d2f\u8ba1|\u9884\u8ba1|\u5efa\u8bae|\u6ce8\u610f|\u5019\u9009\u4fe1\u53f7|\u5171\u62a5\u544a|FAERS|openFDA|DailyMed|\u6a21\u578b\u4f30\u7b97|\u5411\u540e\u66b4\u9732|\u672a\u6765\u5cf0\u503c)[\uff1a:]";
  const normalized = text
    .replace(/[；;]/g, "|")
    .replace(/([。！？!?])\s*(?=\S)/g, "$1|")
    .replace(new RegExp("\\s+(?=" + boundaryLabels + ")", "g"), "|");
  const pieces = normalized
    .split("|")
    .map((part) => part.trim())
    .filter(Boolean);
  return pieces.length ? pieces : ["需要结合剂量、时间和当前状态继续观察。"];
}

function warningSegmentKind(text = "") {
  if (/(?:FAERS|openFDA|DailyMed|\u6765\u6e90|\u53ef\u4fe1\u5ea6|\u8bc1\u636e|\u5019\u9009\u4fe1\u53f7)/i.test(text)) return "evidence";
  if (/(?:\u5efa\u8bae|\u6ce8\u610f|\u8bf7|\u9700|\u8054\u7cfb|\u533b\u751f|\u836f\u5e08|\u6025\u6551|\u76d1\u6d4b|\u4fdd\u5b88)/.test(text)) return "action";
  if (/(?:\u5f53\u524d|\u7d2f\u8ba1|\u6700\u5927|\u5355\u6b21|\u66b4\u9732|AUC|Cmax|\u5cf0\u503c|\u6d53\u5ea6|\u9884\u8ba1|mg|g\/L|ug\/L|\u03bcg\/L)/i.test(text)) return "metric";
  return "detail";
}

function forecastWarningItem(forecast) {
  const digits = forecast.peak < 1 ? 3 : forecast.peak < 10 ? 2 : 1;
  const currentText = formatNumber(forecast.current, digits);
  const peakText = formatNumber(forecast.peak, digits);
  return {
    subject: forecast.name,
    level: "Minor",
    levelText: "\u9884\u8b66",
    meta: "\u672a\u6765\u5cf0\u503c",
    note: `\u9884\u8ba1 ${formatDurationMinutes(forecast.minutesToPeak)} \u540e\u63a5\u8fd1\u5cf0\u503c\uff1a${currentText} \u2192 ${peakText} ${forecast.unit}/L\u3002${forecast.effect}\u76f8\u5173\u526f\u4f5c\u7528\u53ef\u80fd\u5728\u8fbe\u5cf0\u524d\u540e\u66f4\u660e\u663e\u3002`,
  };
}

function groupedWarningItems(items = []) {
  const bySubject = new Map();
  items.forEach((item) => {
    const subject = item.subject || "\u672a\u547d\u540d\u98ce\u9669";
    if (!bySubject.has(subject)) bySubject.set(subject, { subject, items: [], topLevel: item.level || "Unknown" });
    const group = bySubject.get(subject);
    group.items.push(item);
    if (riskSortValue(item.level) > riskSortValue(group.topLevel)) group.topLevel = item.level;
  });
  return [...bySubject.values()];
}


function renderWarningNote(note = "") {
  const pieces = splitWarningNote(note);
  if (pieces.length <= 1) {
    return `<div class="warning-note-single" data-kind="${escapeHtml(warningSegmentKind(pieces[0]))}">${escapeHtml(pieces[0])}</div>`;
  }
  return `
    <div class="warning-note-segments">
      ${pieces.map((part) => `<p data-kind="${escapeHtml(warningSegmentKind(part))}">${escapeHtml(part)}</p>`).join("")}
    </div>
  `;
}

function renderWarningGroup(group) {
  const topItem = group.items.reduce((best, item) => riskSortValue(item.level) > riskSortValue(best.level) ? item : best, group.items[0]);
  const badgeText = topItem.levelText || riskLevelLabel(group.topLevel);
  const rows = group.items.map((item) => `
    <div class="warning-row">
      <span>${escapeHtml(item.meta || "\u63d0\u9192")}</span>
      ${renderWarningNote(item.note)}
    </div>
  `).join("");
  return `
    <article class="warning-group">
      <header>
        <div class="warning-subject">${escapeHtml(group.subject)}</div>
        <span class="badge ${escapeHtml(group.topLevel)}">${escapeHtml(badgeText)}</span>
      </header>
      ${rows}
    </article>
  `;
}

function renderPeakForecastPanel(items = []) {
  if (!items.length) return "";
  const rows = items.map((item) => `
    <article class="peak-forecast-card">
      <header>
        <strong>${escapeHtml(item.subject)}</strong>
        <span>${escapeHtml(item.levelText || "\u9884\u8b66")}</span>
      </header>
      <div class="peak-forecast-meta">${escapeHtml(item.meta || "\u672a\u6765\u5cf0\u503c")}</div>
      ${renderWarningNote(item.note)}
    </article>
  `).join("");
  return `
    <section class="peak-forecast-panel">
      <div class="peak-forecast-title">
        <strong>\u672a\u6765\u5cf0\u503c\u89c2\u5bdf</strong>
        <span>${items.length} \u9879</span>
      </div>
      <div class="peak-forecast-list">${rows}</div>
    </section>
  `;
}

function renderPeakForecastWarning(items = []) {
  const target = $("peakForecastWarning");
  if (!target) return;
  if (!items.length) {
    target.className = "peak-forecast-host hidden";
    target.innerHTML = "";
    return;
  }
  target.className = "peak-forecast-host";
  target.innerHTML = renderPeakForecastPanel(items);
}
function conciseWarningSummary(note = "", maxSegments = 2) {
  return splitWarningNote(note).slice(0, maxSegments).join("?");
}

function sideEffectRiskSummary(risk = {}) {
  const subject = riskSubjectText(risk);
  const level = riskLevelLabel(risk.risk_level);
  if (risk.risk_kind === "dose") {
    const note = conciseWarningSummary(risk.note || "", 2);
    return note ? `${level}\u5242\u91cf/\u8fc7\u91cf\u63d0\u9192\uff1a${note}` : `${subject} \u5b58\u5728 ${level} \u5242\u91cf/\u8fc7\u91cf\u63d0\u9192\u3002`;
  }
  if (risk.risk_kind === "model") {
    const note = conciseWarningSummary(risk.note || "", 2);
    return note ? `${level}\u6a21\u578b\u63d0\u9192\uff1a${note}` : `${subject} \u7684 PopPK \u6a21\u578b\u63d0\u793a\u9700\u8981\u5173\u6ce8\u3002`;
  }
  if (risk.risk_kind === "signal") {
    const note = conciseWarningSummary(risk.note || "", 1);
    return note ? `${level}\u5019\u9009\u4fe1\u53f7\uff1a${note}` : `${subject} \u6709\u516c\u5f00\u836f\u7269\u8b66\u6212\u5019\u9009\u4fe1\u53f7\uff0c\u9700\u7ed3\u5408\u75c7\u72b6\u89c2\u5bdf\u3002`;
  }
  const type = interactionTypeLabel(risk.interaction_type || "");
  const typeText = type && type !== "\u672a\u5206\u7c7b" ? `\uff0c\u7c7b\u578b\uff1a${type}` : "";
  return `${subject}\uff1a${level}\u8054\u7528\u51b2\u7a81${typeText}\u3002\u5b8c\u6574\u6765\u6e90\u3001raw_levels \u548c labels \u5728\u4e0b\u65b9\u5b8c\u6574\u98ce\u9669\u5217\u8868\u67e5\u770b\u3002`;
}

function renderWarningSummaryRow(item) {
  return `
    <article class="warning-summary-row">
      <header>
        <strong>${escapeHtml(item.subject)}</strong>
        <span class="badge ${escapeHtml(item.level)}">${escapeHtml(item.levelText || riskLevelLabel(item.level))}</span>
      </header>
      <div class="warning-summary-meta">${escapeHtml(item.meta || "\u63d0\u9192")}</div>
      <p>${escapeHtml(item.note)}</p>
    </article>
  `;
}

function renderSideEffectWarning() {
  const target = $("sideEffectWarning");
  if (!target) return;
  const risks = state.activeRisks || [];
  const visibleRiskItems = riskItemsForMode(risks);
  const highRisks = visibleRiskItems.filter((risk) => riskSortValue(risk.risk_level) >= 3);
  const summaryLimit = state.advancedMode ? 2 : 2;
  const summaryRisks = highRisks.slice(0, summaryLimit);
  const hiddenRiskCount = Math.max(0, highRisks.length - summaryRisks.length);
  const forecastWarnings = exposureForecasts(activeEntries())
    .slice(0, state.advancedMode ? 4 : 2)
    .map(forecastWarningItem);
  renderPeakForecastWarning(forecastWarnings);
  const modelWarnings = activeEntries().flatMap((entry) => {
    const substance = state.substanceById.get(entry.substanceId) || { id: entry.substanceId };
    const params = adjustedPkParams(entry, substance);
    return (params.warnings || []).map((warning) => ({
      subject: substanceName(entry.substanceId),
      level: "Moderate",
      meta: "\u6a21\u578b\u534f\u53d8\u91cf",
      note: conciseWarningSummary(warning, 1),
    }));
  }).slice(0, Math.max(0, summaryLimit - summaryRisks.length));
  const warningItems = [
    ...summaryRisks.map((risk) => ({
      subject: riskSubjectText(risk),
      level: risk.risk_level,
      meta: risk.risk_kind === "dose"
        ? "\u5242\u91cf/\u8fc7\u91cf"
        : risk.risk_kind === "model"
          ? "\u4ee3\u8c22\u6a21\u578b"
          : risk.risk_kind === "signal"
            ? "\u5019\u9009\u4fe1\u53f7"
            : "\u8054\u7528\u51b2\u7a81",
      note: sideEffectRiskSummary(risk),
    })),
    ...modelWarnings,
  ];
  if (!warningItems.length) {
    target.className = forecastWarnings.length ? "side-effect-warning empty hidden" : "side-effect-warning empty";
    target.textContent = forecastWarnings.length
      ? ""
      : (state.advancedMode
        ? "\u6682\u65e0\u526f\u4f5c\u7528\u3001\u8fc7\u91cf\u6216\u6a21\u578b\u5f02\u5e38\u8b66\u544a\uff1bUnknown \u8868\u793a\u8d44\u6599\u4e0d\u8db3\uff0c\u4e0d\u4ee3\u8868\u5b89\u5168\u3002"
        : "\u6682\u65e0\u660e\u786e\u526f\u4f5c\u7528\u6216\u8fc7\u91cf\u63d0\u9192\u3002\u8d44\u6599\u4e0d\u5168\u65f6\u4ecd\u9700\u4fdd\u5b88\u4f7f\u7528\u3002");
    return;
  }
  target.className = "side-effect-warning compact-warning-summary";
  const title = state.advancedMode ? "\u526f\u4f5c\u7528/\u8fc7\u91cf\u6458\u8981" : "\u9700\u5173\u6ce8\u63d0\u9192";
  const countText = hiddenRiskCount
    ? `${warningItems.length} \u6761\u6458\u8981 \u00b7 \u4e0b\u65b9\u8fd8\u6709 ${hiddenRiskCount} \u6761`
    : `${warningItems.length} \u6761\u6458\u8981`;
  const footer = hiddenRiskCount
    ? `\u4e0b\u65b9\u5b8c\u6574\u98ce\u9669\u5217\u8868\u5c55\u793a\u5168\u90e8 ${visibleRiskItems.length} \u6761\u8bb0\u5f55\uff0c\u5305\u62ec raw_levels\u3001labels \u548c\u6765\u6e90\u5b57\u6bb5\u3002`
    : "\u5b8c\u6574\u6765\u6e90\u3001\u8bc1\u636e\u5b57\u6bb5\u548c\u539f\u59cb\u6807\u7b7e\u5728\u4e0b\u65b9\u98ce\u9669\u5217\u8868\u4e2d\u67e5\u770b\u3002";
  target.innerHTML = `
    <div class="warning-head">
      <strong>${escapeHtml(title)}</strong>
      <span>${escapeHtml(countText)}</span>
    </div>
    <div class="warning-summary-list">${warningItems.map(renderWarningSummaryRow).join("")}</div>
    <div class="warning-footer">${escapeHtml(footer)}</div>
  `;
}

function localizedLabel(map, value, fallback = "\u672a\u77e5") {
  if (!value) return fallback;
  return map[value] || value;
}

function riskLevelLabel(value) {
  return localizedLabel(riskLevelLabels, value, value || "\u672a\u77e5");
}

function confidenceLabel(value) {
  return localizedLabel(confidenceLabels, value, value || "\u672a\u77e5");
}

function sourceTierLabel(value) {
  return localizedLabel(sourceTierLabels, value, value || "\u672a\u77e5\u6765\u6e90");
}

function interactionTypeLabel(value) {
  return localizedLabel(interactionTypeLabels, value, value || "\u672a\u5206\u7c7b");
}

function categoryLabel(value) {
  return localizedLabel(categoryLabels, value, value || "\u672a\u5206\u7c7b");
}


const substanceEffectProfiles = {
  caffeine: {
    terms: ["caffeine"],
    effect: "\u4e2d\u67a2\u5174\u594b\uff0c\u53ef\u63d0\u9ad8\u8b66\u89c9\u6027\u3001\u5fc3\u7387\uff0c\u5e76\u5ef6\u8fdf\u7761\u7720\u3002",
    mechanism: "\u4e3b\u8981\u4e0e\u817a\u82f7\u53d7\u4f53\u62ee\u6297\u6709\u5173\u3002",
  },
  ethanol: {
    terms: ["ethanol", "alcohol"],
    effect: "\u4e2d\u67a2\u6291\u5236\uff0c\u53ef\u964d\u4f4e\u53cd\u5e94\u901f\u5ea6\u3001\u5224\u65ad\u529b\u548c\u8fd0\u52a8\u534f\u8c03\u3002",
    mechanism: "\u4e0e GABA/\u8c37\u6c28\u9178\u901a\u8def\u76f8\u5173\uff1b\u4e0e\u9547\u9759\u836f\u8054\u7528\u65f6\u98ce\u9669\u4e0a\u5347\u3002",
  },
  lorazepam: {
    terms: ["lorazepam"],
    effect: "\u82ef\u4e8c\u6c2e\u5353\u7c7b\u9547\u9759\u3001\u6297\u7126\u8651\u3001\u6297\u60ca\u53a5\u4f5c\u7528\u3002",
    mechanism: "GABA-A \u53d7\u4f53\u6b63\u5411\u53d8\u6784\u8c03\u8282\uff1b\u4e0e\u9152\u7cbe\u6216\u5176\u4ed6\u9547\u9759\u836f\u53e0\u52a0\u65f6\u9700\u91cd\u70b9\u8b66\u60d5\u3002",
  },
  zolpidem: {
    terms: ["zolpidem"],
    effect: "\u50ac\u7720\u9547\u9759\uff0c\u4e3b\u8981\u7528\u4e8e\u77ed\u671f\u7761\u7720\u8bf1\u5bfc\u3002",
    mechanism: "\u4f5c\u7528\u4e8e GABA-A \u82ef\u4e8c\u6c2e\u5353\u4f4d\u70b9\u76f8\u5173\u901a\u8def\u3002",
  },
  sertraline: {
    terms: ["sertraline"],
    effect: "SSRI \u7c7b\u6297\u6291\u90c1/\u6297\u7126\u8651\u4f5c\u7528\u3002",
    mechanism: "\u63d0\u9ad8\u7a81\u89e6\u95f4 5-HT \u4fe1\u53f7\uff1b\u4e0e\u5176\u4ed6\u4fc3 5-HT \u836f\u7269\u53e0\u52a0\u65f6\u5173\u6ce8\u8840\u6e05\u7d20\u6bd2\u6027\u3002",
  },
  methylphenidate: {
    terms: ["methylphenidate"],
    effect: "\u4e2d\u67a2\u5174\u594b\uff0c\u63d0\u9ad8\u6ce8\u610f\u529b\u548c\u89c9\u9192\u5ea6\u3002",
    mechanism: "\u6291\u5236\u591a\u5df4\u80fa/\u53bb\u7532\u80be\u4e0a\u817a\u7d20\u518d\u6444\u53d6\uff1b\u53ef\u589e\u52a0\u5fc3\u7387\u548c\u8840\u538b\u3002",
  },
  tandospirone: {
    terms: ["tandospirone"],
    effect: "\u6297\u7126\u8651\u4f5c\u7528\uff0c\u901a\u5e38\u9547\u9759\u6027\u8f83\u82ef\u4e8c\u6c2e\u5353\u7c7b\u5f31\u3002",
    mechanism: "5-HT1A \u53d7\u4f53\u90e8\u5206\u6fc0\u52a8\u76f8\u5173\u3002",
  },
  ibuprofen: {
    terms: ["ibuprofen"],
    effect: "NSAID \u9547\u75db\u3001\u6297\u708e\u3001\u9000\u70ed\u3002",
    mechanism: "\u4e3b\u8981\u4e0e COX \u6291\u5236\u548c\u524d\u5217\u817a\u7d20\u5408\u6210\u4e0b\u964d\u6709\u5173\u3002",
  },
  acetaminophen: {
    terms: ["acetaminophen", "paracetamol"],
    effect: "\u89e3\u70ed\u9547\u75db\uff0c\u6297\u708e\u4f5c\u7528\u5f31\u3002",
    mechanism: "\u8fc7\u91cf\u65f6\u91cd\u70b9\u98ce\u9669\u662f\u809d\u6bd2\u6027\uff0c\u9700\u6309 24 \u5c0f\u65f6\u7d2f\u8ba1\u5242\u91cf\u8bc4\u4f30\u3002",
  },
  grapefruit_juice: {
    terms: ["grapefruit", "grapefruit_juice"],
    effect: "\u836f\u98df\u4e92\u4f5c\u7528\u6e90\uff0c\u53ef\u663e\u8457\u6539\u53d8\u90e8\u5206\u836f\u7269\u66b4\u9732\u3002",
    mechanism: "\u53ef\u6291\u5236\u80a0\u9053 CYP3A4/P-gp\uff0c\u5bfc\u81f4\u90e8\u5206\u5e95\u7269\u8840\u836f\u6d53\u5ea6\u4e0a\u5347\u3002",
  },
  tea_polyphenols: {
    terms: ["tea_polyphenols", "egcg"],
    effect: "\u81b3\u98df/\u8865\u5145\u5242\u6210\u5206\uff0c\u5e38\u89c1\u4e3a\u6297\u6c27\u5316\u76f8\u5173\u7528\u9014\u3002",
    mechanism: "\u9ad8\u5242\u91cf EGCG \u9700\u5173\u6ce8\u809d\u635f\u4f24\u4fe1\u53f7\uff0c\u4e5f\u53ef\u80fd\u5f71\u54cd\u90e8\u5206\u836f\u7269\u5438\u6536\u6216\u8f6c\u8fd0\u3002",
  },
};

const categoryEffectSummaries = {
  Stimulant: "\u5174\u594b\u7c7b\u4f5c\u7528\uff1b\u901a\u5e38\u63d0\u9ad8\u89c9\u9192\u5ea6\u3001\u5fc3\u7387\u6216\u4ea4\u611f\u795e\u7ecf\u6d3b\u6027\u3002",
  Depressant: "\u6291\u5236\u7c7b\u4f5c\u7528\uff1b\u901a\u5e38\u8868\u73b0\u4e3a\u9547\u9759\u3001\u53cd\u5e94\u53d8\u6162\u6216\u4e2d\u67a2\u6291\u5236\u3002",
  Dissociative: "\u89e3\u79bb\u7c7b\u4f5c\u7528\uff1b\u53ef\u80fd\u6539\u53d8\u611f\u77e5\u3001\u8fd0\u52a8\u534f\u8c03\u548c\u610f\u8bc6\u72b6\u6001\u3002",
  "Supplement/Food": "\u98df\u7269/\u8865\u5145\u5242\uff1b\u91cd\u70b9\u770b\u5176\u5bf9\u4ee3\u8c22\u9176\u3001\u8f6c\u8fd0\u4f53\u548c\u5438\u6536\u7684\u5f71\u54cd\u3002",
  Food: "\u98df\u7269\u6e90\uff1b\u91cd\u70b9\u770b\u836f\u98df\u76f8\u4e92\u4f5c\u7528\u548c\u5438\u6536/\u4ee3\u8c22\u5f71\u54cd\u3002",
  DrugLabel: null,
  Drug: null,
};

const modelTypeLabels = {
  one_compartment_first_order_absorption: "\u4e00\u5ba4\u6a21\u578b/\u4e00\u9636\u5438\u6536",
  instant_elimination: "\u77ac\u65f6\u5438\u6536/\u4e00\u9636\u6d88\u9664",
  ethanol_zero_order_widmark: "\u4e59\u9187 Widmark/\u8fd1\u4f3c\u96f6\u7ea7\u6d88\u9664",
};

function findEffectProfile(substance = {}) {
  const haystack = `${substance.id || ""} ${substance.name_en || ""} ${substance.name_zh || ""} ${substance.identifiers?.aliases || ""}`.toLowerCase();
  return Object.values(substanceEffectProfiles).find((profile) => profile.terms.some((term) => haystack.includes(String(term).toLowerCase())));
}


function sentenceText(text) {
  const value = String(text || "").trim();
  if (!value) return "";
  return /[。！？.!?]$/.test(value) ? value : `${value}。`;
}

function shortEvidenceText(value, limit = 220) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text) return "";
  return text.length > limit ? `${text.slice(0, limit - 1)}?` : text;
}

function primaryRemoteDrugEffect(substance = {}) {
  const rows = normalizeRemoteList(substance.remote_evidence?.drug_effects);
  if (!rows.length) return null;
  const row = rows.find((item) => item.mechanism_of_action || item.target) || rows[0];
  const effectText = shortEvidenceText(row.effect_text || row.evidence || row.mechanism_of_action, 260);
  const mechanism = shortEvidenceText(row.mechanism_of_action, 220);
  const target = [row.target, row.action_type].filter(Boolean).join(" / ");
  return { row, effectText, mechanism, target };
}

function remotePkSummary(substance = {}) {
  const rows = normalizeRemoteList(substance.remote_evidence?.pharmacokinetics);
  const halfLife = substance.base_half_life || rows.find((row) => row.half_life_hours !== null && row.half_life_hours !== undefined)?.half_life_hours;
  const parts = [];
  if (halfLife) parts.push(`\u534a\u8870\u671f ${Number(halfLife).toFixed(1)}h`);
  const clearance = rows.find((row) => row.clearance)?.clearance;
  if (clearance) parts.push(`\u6e05\u9664\u7387 ${clearance}`);
  const vd = rows.find((row) => row.volume_distribution)?.volume_distribution;
  if (vd) parts.push(`Vd ${vd}`);
  return parts.join(" \u00b7 ");
}

function substanceCypTags(substance = {}) {
  const localTags = substance.cyp_tags || [];
  const remoteTags = normalizeRemoteList(substance.remote_evidence?.enzyme_relations).map((row) => row.tag || [row.enzyme, row.relation].filter(Boolean).join("_")).filter(Boolean);
  return [...new Set([...localTags, ...remoteTags])];
}

function effectDisplay(substance = {}) {
  const profile = findEffectProfile(substance);
  if (profile?.effect) return { text: profile.effect, profile, known: true };
  const remote = primaryRemoteDrugEffect(substance);
  if (remote) {
    const text = remote.effectText || remote.mechanism || (remote.target ? `\u9776\u70b9\uff1a${remote.target}` : "\u5df2\u83b7\u53d6\u8fdc\u7a0b\u836f\u6548\u8bc1\u636e");
    return {
      text,
      profile: { mechanism: remote.mechanism || "", target: remote.target || "", source: remote.row?.source_name || "" },
      known: true,
      remote,
    };
  }
  const categoryText = categoryEffectSummaries[substance.category];
  if (categoryText) return { text: categoryText, profile: null, known: true };
  return { text: "\u6682\u65e0", profile: null, known: false };
}
function formatCypTag(tag) {
  return String(tag || "")
    .replace(/_substrate$/i, " \u5e95\u7269")
    .replace(/_inhibitor$/i, " \u6291\u5236\u5242")
    .replace(/_inducer$/i, " \u8bf1\u5bfc\u5242")
    .replace(/_/g, " ");
}

function pkSummary(substance = {}) {
  const parts = [];
  if (substance.base_half_life) parts.push(`\u534a\u8870\u671f ${Number(substance.base_half_life).toFixed(1)}h`);
  if (substance.base_onset) parts.push(`\u8d77\u6548 ${formatNumber(substance.base_onset, 0)}min`);
  if (substance.base_duration) parts.push(`\u6301\u7eed ${formatNumber(substance.base_duration, 0)}min`);
  const remotePk = remotePkSummary(substance);
  if (remotePk && !parts.join(" ").includes(remotePk)) parts.push(remotePk);
  return parts.join(" \u00b7 ");
}

function substanceEffectSummary(substance = {}, params = null) {
  const effect = effectDisplay(substance);
  const lines = [];
  lines.push(`\u4f5c\u7528\uff1a${sentenceText(effect.text)}`);
  if (effect.profile?.mechanism) lines.push(`\u673a\u5236\uff1a${sentenceText(effect.profile.mechanism)}`);
  if (effect.remote?.target) lines.push(`\u9776\u70b9/\u4f5c\u7528\uff1a${sentenceText(effect.remote.target)}`);
  if (effect.remote?.row?.source_name) lines.push(`\u6765\u6e90\uff1a${sentenceText(effect.remote.row.source_name)}`);
  const cyp = (substance.cyp_tags || []).map(formatCypTag).filter(Boolean);
  if (cyp.length) lines.push(`\u4ee3\u8c22/\u9176\uff1a${cyp.join("\uff0c")}\u3002`);
  const pk = pkSummary(substance);
  if (pk) lines.push(`\u836f\u4ee3\uff1a${pk}\u3002`);
  if (params) lines.push(`\u5f53\u524d\u6a21\u578b\uff1a${modelTypeLabels[params.modelType] || params.modelType}\uff1b${popPkExplanation(params)}\uff1b\u4e2a\u4f53\u534a\u8870\u671f ${params.adjustedHalfLifeHours.toFixed(1)}h\u3002`);
  return lines.join(" ");
}

function compactSubstanceEffect(substance = {}) {
  return effectDisplay(substance).text;
}

function consumerSubstanceEffect(substance = {}) {
  const lines = [`\u4f5c\u7528\uff1a${compactSubstanceEffect(substance)}`];
  const pk = pkSummary(substance);
  if (pk) lines.push(`\u65f6\u95f4\uff1a${pk}\u3002`);
  const cyp = substanceCypTags(substance).map(formatCypTag).filter(Boolean).slice(0, 3);
  if (cyp.length) lines.push(`\u4ee3\u8c22\u8981\u70b9\uff1a${cyp.join("\uff0c")}\u3002`);
  lines.push("\u4fdd\u5b58\u540e\u4f1a\u6309\u4f60\u7684\u4f53\u91cd\u3001\u4f53\u8102\u3001\u5e74\u9f84\u3001\u7761\u7720\u548c\u4f53\u6e29\u4fee\u6b63\u66f2\u7ebf\u4e0e\u98ce\u9669\u3002");
  return lines.join(" ");
}

function renderSelectedSubstanceInfo() {
  const target = $("selectedSubstanceInfo");
  if (!target) return;
  const substance = selectedSubstance();
  if (!substance) {
    target.textContent = "\u672a\u9009\u62e9\u7269\u8d28\u3002";
    return;
  }
  target.textContent = state.advancedMode ? substanceEffectSummary(substance) : consumerSubstanceEffect(substance);
}

function localizeInteractionNote(note) {
  if (!note) return "";
  const riskPattern = /Contraindicated|Major|Moderate|Minor|Dangerous|Unsafe|Synergy|Low Risk|NoKnownClinicalSignificance|Unknown/g;
  return String(note)
    .replace("DDInter 2.0 severity=", "DDInter 2.0 \u98ce\u9669\u7b49\u7ea7=")
    .replace("raw_levels=", "\u539f\u59cb\u7b49\u7ea7=")
    .replace("labels=", "\u6e90\u540d\u79f0=")
    .replace(riskPattern, (match) => riskLevelLabel(match));
}

function substanceName(id) {
  const item = state.substanceById.get(id);
  return item?.name_zh || item?.name_en || id;
}

function substanceLabel(item) {
  const zh = item.name_zh ? `${item.name_zh} / ` : "";
  return `${zh}${item.name_en || item.id}`;
}

function routeLabel(value) {
  return routeProfiles[value]?.label || value || "未记录";
}

function stomachLabel(value) {
  return stomachProfiles[value]?.label || value || "未记录";
}

function metabolicLabel(value) {
  return metabolicProfiles[value]?.label || value || "\u6b63\u5e38\u4ee3\u8c22";
}

function hydrationLabel(value) {
  return hydrationProfiles[value]?.label || value || "\u6b63\u5e38\u6c34\u5408";
}

function criticalStateLabel(value) {
  return criticalStateProfiles[value]?.label || value || "\u7a33\u5b9a";
}

function coreTempLabel(value) {
  const temp = Number(value || 37);
  if (temp >= 39) return "\u53d1\u70e7";
  if (temp >= 37.8) return "\u53d1\u70ed";
  return "\u6b63\u5e38";
}

function formatNumber(value, fractionDigits = 1) {
  return Number(value || 0).toLocaleString("zh-CN", {
    maximumFractionDigits: fractionDigits,
    minimumFractionDigits: 0,
  });
}

function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (!Number.isFinite(value) || value <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let size = value;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${formatNumber(size, size >= 10 || index === 0 ? 0 : 1)} ${units[index]}`;
}

function selectedSubstance() {
  return state.substanceById.get($("substanceSelect")?.value);
}

function selectedSourceTerm() {
  const explicit = ($("sourceTerm")?.value || "").trim();
  if (explicit) return explicit;
  const selected = selectedSubstance();
  return selected?.name_en || selected?.id || "";
}

function isEthanolSubstance(value) {
  const item = typeof value === "string" ? state.substanceById.get(value) || { id: value } : value;
  const haystack = `${item?.id || ""} ${item?.name_en || ""} ${item?.name_zh || ""} ${item?.identifiers?.aliases || ""}`.toLowerCase();
  return haystack.includes("ethanol") || haystack.includes("alcohol") || haystack.includes("乙醇") || haystack.includes("酒精");
}

function calculateEthanolDose() {
  const volumeMl = clampNumber($("drinkVolumeInput")?.value, 500, 0, 10000);
  const abvPct = clampNumber($("drinkAbvInput")?.value, 5, 0, 100);
  const grams = volumeMl * (abvPct / 100) * ethanolDensityGPerMl;
  return { volumeMl, abvPct, grams };
}

function syncDoseSlider(value) {
  const slider = $("doseSlider");
  if (!slider) return;
  const dose = Math.max(0, Number(value || 0));
  if (dose > Number(slider.max)) slider.max = String(Math.ceil(dose));
  slider.value = String(dose);
}

function syncEthanolCalculator(writeDose = true) {
  const panel = $("ethanolCalculator");
  if (!panel) return;
  const isEthanol = isEthanolSubstance(selectedSubstance());
  panel.classList.toggle("hidden", !isEthanol);
  if (!isEthanol) return;
  const dose = calculateEthanolDose();
  $("unitSelect").value = "g";
  $("routeSelect").value = "Oral";
  $("ethanolDosePreview").textContent = `${formatNumber(dose.volumeMl, 0)}ml × ${formatNumber(dose.abvPct, 1)}%vol ≈ ${formatNumber(dose.grams, 1)}g 乙醇`;
  if (writeDose) {
    $("dosageInput").value = dose.grams.toFixed(1);
    syncDoseSlider(dose.grams);
  }
}

function formatEthanolEntry(entry) {
  const ethanol = entry.ethanol;
  if (!ethanol) return "";
  return `${formatNumber(ethanol.volumeMl, 0)}ml × ${formatNumber(ethanol.abvPct, 1)}%vol = ${formatNumber(ethanol.grams, 1)}g 乙醇`;
}

function toDateTimeLocal(timestamp) {
  const date = new Date(timestamp);
  const offsetMs = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

function fromDateTimeLocal(value) {
  const timestamp = value ? new Date(value).getTime() : Date.now();
  return Number.isFinite(timestamp) ? timestamp : Date.now();
}

function resetIntakeTime() {
  const input = $("intakeTimeInput");
  if (input) input.value = toDateTimeLocal(Date.now());
}

function sameLocalDate(a, b) {
  const left = new Date(a);
  const right = new Date(b);
  return left.getFullYear() === right.getFullYear()
    && left.getMonth() === right.getMonth()
    && left.getDate() === right.getDate();
}

function formatAxisTime(timestamp, viewportStart = timestamp, viewportEnd = timestamp) {
  const date = new Date(timestamp);
  const time = date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false });
  const showDate = !sameLocalDate(viewportStart, viewportEnd);
  return {
    time,
    date: showDate ? date.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" }) : "",
  };
}

function formatTooltipTime(timestamp) {
  return new Date(timestamp).toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function minutesSince(timestamp) {
  return (Date.now() - timestamp) / 60000;
}

function minutesBetween(fromTimestamp, toTimestamp) {
  return (toTimestamp - fromTimestamp) / 60000;
}

function normalizeCoreTemp(value) {
  const temp = Number(value || 37);
  if (!Number.isFinite(temp)) return 37;
  if (temp >= 39) return 39.5;
  if (temp >= 37.8) return 38.3;
  return 37;
}

function getProfileFromInputs() {
  return {
    weightKg: clampNumber($("weightInput")?.value, 70, 25, 220),
    heightCm: clampNumber($("heightInput")?.value, 170, 120, 230),
    bodyFatPct: clampNumber($("bodyFatInput")?.value, 20, 3, 70),
    ageYears: clampNumber($("ageInput")?.value, 35, 0, 110),
    sleepDebtHours: clampNumber($("sleepDebtInput")?.value, 0, 0, 72),
    coreTempC: normalizeCoreTemp($("coreTempInput")?.value),
    eGfr: 120,
    childPughScore: 5,
    heartRateBpm: 70,
    metabolicType: "EM",
    hydrationState: "Normal",
    criticalState: "Stable",
  };
}

function saveProfile() {
  localStorage.setItem(profileStorageKey, JSON.stringify(getProfileFromInputs()));
}

function setInputValue(id, value) {
  const element = $(id);
  if (element) element.value = value;
}

function loadProfile() {
  let profile = {
    weightKg: 70,
    heightCm: 170,
    bodyFatPct: 20,
    ageYears: 35,
    sleepDebtHours: 0,
    coreTempC: 37,
  };
  try {
    profile = { ...profile, ...JSON.parse(localStorage.getItem(profileStorageKey) || "{}") };
  } catch {}
  setInputValue("weightInput", profile.weightKg);
  setInputValue("heightInput", profile.heightCm);
  setInputValue("bodyFatInput", profile.bodyFatPct);
  setInputValue("ageInput", profile.ageYears);
  setInputValue("sleepDebtInput", profile.sleepDebtHours);
  setInputValue("coreTempInput", normalizeCoreTemp(profile.coreTempC));
}

function clampNumber(value, fallback, min, max) {
  const num = Number(value);
  if (!Number.isFinite(num)) return fallback;
  return Math.min(Math.max(num, min), max);
}

function activeEntries() {
  return state.journal.filter((entry) => {
    const substance = state.substanceById.get(entry.substanceId);
    const params = adjustedPkParams(entry, substance);
    const activeWindow = Math.max((params.adjustedHalfLifeHours || 4) * 6 * 60, Number(substance?.base_duration || 360), 60);
    return minutesSince(entry.timestamp) <= activeWindow;
  });
}

function loadJournal() {
  try {
    state.journal = JSON.parse(localStorage.getItem(storageKey) || "[]");
  } catch {
    state.journal = [];
  }
  let migrated = false;
  state.journal = state.journal.map((entry, index) => {
    if (entry.id) return entry;
    migrated = true;
    return { ...entry, id: `legacy_${entry.timestamp || Date.now()}_${index}` };
  });
  if (migrated) saveJournal();
}

function saveJournal() {
  localStorage.setItem(storageKey, JSON.stringify(state.journal));
}

function riskSortValue(risk) {
  return {
    Contraindicated: 6,
    Dangerous: 6,
    Major: 5,
    Unsafe: 5,
    Moderate: 4,
    Synergy: 3,
    Minor: 2,
    "Low Risk": 1,
    Unknown: 1,
    NoKnownClinicalSignificance: 0,
  }[risk] ?? 1;
}

function doseRuleMatches(rule, substance) {
  if (!substance) return false;
  const id = String(substance.id || "").toLowerCase();
  const subjectId = String(rule.subject_id || rule.key || "").toLowerCase();
  if (subjectId && id === subjectId) return true;
  const names = [substance.name_en, substance.name_zh].filter(Boolean).map((value) => String(value).toLowerCase());
  const aliases = String(substance.identifiers?.aliases || "").split("|").map((value) => value.trim().toLowerCase()).filter(Boolean);
  const terms = rule.match_terms || rule.match || [rule.subject_id, rule.key].filter(Boolean);
  return terms.some((term) => {
    const normalized = term.toLowerCase();
    return id === normalized || names.includes(normalized) || aliases.includes(normalized);
  });
}

function doseAmountForRule(entry, rule) {
  const dose = Number(entry.dosage || 0);
  if (!Number.isFinite(dose) || dose <= 0) return null;
  const unit = String(entry.unit || "mg").toLowerCase();
  if (rule.unit === "mg") {
    if (unit === "mg") return dose;
    if (unit === "g") return dose * 1000;
    if (unit === "ug" || unit === "mcg") return dose / 1000;
    return null;
  }
  if (rule.unit === "g") {
    if (entry.ethanol?.grams) return Number(entry.ethanol.grams);
    if (unit === "g") return dose;
    if (unit === "mg") return dose / 1000;
    if (unit === "ug" || unit === "mcg") return dose / 1000000;
    return null;
  }
  return null;
}


function doseRouteMatches(entry = {}, rule = {}) {
  const route = String(rule.route || "").trim().toLowerCase();
  if (!route || ["any", "all", "unspecified", "unknown"].includes(route)) return true;
  const entryRoute = String(entry.route || "").trim().toLowerCase();
  if (!entryRoute || entryRoute === "other") return true;
  const routeAliases = {
    oral: ["oral", "po", "by mouth"],
    sublingual: ["sublingual", "sl"],
    iv: ["iv", "intravenous", "injection"],
    insufflated: ["insufflated", "intranasal", "nasal"],
    topical: ["topical", "transdermal"],
  };
  const aliases = routeAliases[entryRoute] || [entryRoute];
  return aliases.some((alias) => route === alias || route.includes(alias));
}

function evaluateDoseRisks() {
  const now = Date.now();
  const risks = [];
  const rules = state.doseRules?.length ? state.doseRules : doseSafetyRules;
  for (const rule of rules) {
    const windowHours = Number(rule.window_hours ?? rule.windowHours ?? 24);
    const rows = [];
    for (const entry of state.journal) {
      const substance = state.substanceById.get(entry.substanceId);
      if (!doseRuleMatches(rule, substance)) continue;
      if (!doseRouteMatches(entry, rule)) continue;
      if (!entry.timestamp || entry.timestamp > now) continue;
      const ageHours = (now - entry.timestamp) / 3600000;
      if (ageHours > windowHours) continue;
      const amount = doseAmountForRule(entry, rule);
      if (amount === null) continue;
      rows.push({ entry, substance, amount });
    }
    if (!rows.length) continue;
    const total = rows.reduce((sum, row) => sum + row.amount, 0);
    const maxSingle = Math.max(...rows.map((row) => row.amount));
    const breached = rule.thresholds
      .filter((threshold) => (threshold.kind === "single" ? maxSingle : total) >= threshold.limit)
      .sort((a, b) => riskSortValue(b.level) - riskSortValue(a.level) || b.limit - a.limit);
    if (!breached.length) continue;
    const threshold = breached[0];
    const primary = rows[0];
    const unitLabel = rule.unit;
    const totalLabel = `${formatNumber(total, rule.unit === "g" ? 1 : 0)} ${unitLabel}`;
    const singleLabel = `${formatNumber(maxSingle, rule.unit === "g" ? 1 : 0)} ${unitLabel}`;
    const windowText = `${windowHours} \u5c0f\u65f6\u7d2f\u8ba1 ${totalLabel}`;
    const noteParts = [
      `${threshold.label}；当前 ${windowText}，最大单次 ${singleLabel}。`,
    ];
    if ((rule.subject_id || rule.key) === "ethanol") {
      const standardDrinks = total / 14;
      const exposure = rows.reduce((acc, row) => {
        const ethanolEntry = {
          ...row.entry,
          dosage: row.amount,
          unit: "g",
          route: row.entry.route || "Oral",
          ethanol: { ...(row.entry.ethanol || {}), grams: row.amount },
        };
        const ethanolSubstance = {
          ...(row.substance || {}),
          id: "ethanol",
          name_zh: "乙醇",
          name_en: "Ethanol",
          category: "Depressant",
          base_onset: row.substance?.base_onset || 30,
          base_half_life: row.substance?.base_half_life || 4,
        };
        const params = adjustedPkParams(ethanolEntry, ethanolSubstance);
        const tHours = minutesBetween(row.entry.timestamp, now) / 60;
        const current = tHours >= 0 ? concentrationAt(tHours, row.amount, params) : 0;
        const peak = exposureMetricsForEntry(ethanolEntry, params, Math.max(6, windowHours)).cmax;
        acc.current += current;
        acc.peak += peak;
        return acc;
      }, { current: 0, peak: 0 });
      const currentText = exposure.current < 0.01 ? "<0.01" : formatNumber(exposure.current, 2);
      const peakText = exposure.peak < 0.01 ? "<0.01" : formatNumber(exposure.peak, 2);
      noteParts.push(`约 ${formatNumber(standardDrinks, 1)} 个标准杯；当前估算残留 ${currentText} g/L，峰值估算 ${peakText} g/L；本条风险按 ${windowHours} 小时摄入总量触发。`);
    }
    noteParts.push("这是本地剂量规则提示，不替代医生、药师或急救判断。")
    risks.push({
      risk_kind: "dose",
      risk_level: threshold.level,
      substance_id: primary.substance.id,
      substance_name: substanceName(primary.substance.id),
      interaction_type: "dose_safety",
      confidence: rule.confidence,
      source_tier: rule.source_tier || rule.sourceTier,
      source_name: rule.source_name || rule.sourceName,
      action: threshold.level === "Contraindicated" || threshold.level === "Major" ? "avoid_or_seek_help" : "monitor_or_reduce_exposure",
      note: noteParts.join(" "),
    });
  }
  return risks;
}


function evaluateModelRisks(entries = activeEntries()) {
  const risks = [];
  entries.forEach((entry) => {
    const substance = state.substanceById.get(entry.substanceId) || {};
    const params = adjustedPkParams(entry, substance);
    if (!params.warnings?.length) return;
    let level = "Moderate";
    if (params.profile.eGfr < 30 || params.profile.childPughScore >= 10 || params.profile.coreTempC > 40.5) level = "Major";
    risks.push({
      risk_kind: "model",
      risk_level: level,
      substance_id: entry.substanceId,
      substance_name: substanceName(entry.substanceId),
      source_tier: "Literature",
      confidence: "Low",
      interaction_type: "pharmacokinetics",
      source_name: "PopPK \u8ba1\u7b97\u5f15\u64ce",
      note: `${params.warnings.join("\u3002")}\u3002${popPkExplanation(params)}`,
    });
  });
  return risks;
}

function renderSubstanceOptions() {
  const select = $("substanceSelect");
  const filter = ($("substanceFilter")?.value || "").trim().toLowerCase();
  const current = select.value;
  const matches = [];
  for (const item of state.substances) {
    const haystack = `${item.id} ${item.name_en || ""} ${item.name_zh || ""} ${item.identifiers?.aliases || ""}`.toLowerCase();
    if (!filter || haystack.includes(filter)) {
      matches.push(item);
      if (matches.length >= 250) break;
    }
  }
  if (filter && !matches.length && remoteEnabled()) {
    scheduleRemoteSubstanceImport(filter).catch((error) => setRemoteApiStatus(`\u8fdc\u7a0b\u68c0\u7d22\u5931\u8d25\uff1a${error.message || error}`, "error"));
  }
  select.innerHTML = "";
  if (!matches.length && filter && remoteEnabled()) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "\u672c\u5730\u65e0\u547d\u4e2d\uff0c\u6b63\u5728\u67e5\u8be2\u8fdc\u7a0b\u6e90...";
    option.disabled = true;
    select.appendChild(option);
  }
  matches.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.id;
    const remoteMark = item.remote_source ? " \u00b7 \u8fdc\u7a0b" : "";
    option.textContent = `${substanceLabel(item)} \u00b7 ${categoryLabel(item.category)}${remoteMark}`;
    select.appendChild(option);
  });
  if (matches.some((item) => item.id === current)) select.value = current;
  syncEthanolCalculator(true);
  renderSelectedSubstanceInfo();
}

function renderMeta() {
  updateKpis();
  renderPmi();
  const meta = state.manifest || {};
  const mode = modeProfile();
  const substanceCount = Number(meta.substances_count || state.substances.length).toLocaleString("zh-CN");
  const interactionCount = Number(meta.interactions_count || 0).toLocaleString("zh-CN");
  const datasetMeta = $("datasetMeta");
  if (datasetMeta) {
    datasetMeta.textContent = state.advancedMode
      ? `\u6570\u636e\u96c6 ${meta.dataset_version || "\u672a\u77e5\u7248\u672c"} \u00b7 ${substanceCount} \u4e2a\u7269\u8d28 \u00b7 ${interactionCount} \u6761\u76f8\u4e92\u4f5c\u7528`
      : `\u672c\u5730\u5b89\u5168\u5e93\u5df2\u52a0\u8f7d \u00b7 ${substanceCount} \u4e2a\u7269\u8d28 \u00b7 \u6570\u636e\u4e0d\u79bb\u7aef`;
  }
  const profile = getProfileFromInputs();
  const profileQuickSummary = $("profileQuickSummary");
  if (profileQuickSummary) {
    profileQuickSummary.textContent = `${profile.weightKg}kg / ${profile.heightCm}cm / ${profile.ageYears}\u5c81 / \u4f53\u8102 ${profile.bodyFatPct}% / \u7761\u7720 ${profile.sleepDebtHours}h / ${coreTempLabel(profile.coreTempC)}`;
  }
  const modelMeta = $("modelMeta");
  if (modelMeta) {
    modelMeta.textContent = state.advancedMode
      ? `${profile.weightKg}kg \u00b7 ${profile.heightCm}cm \u00b7 ${profile.ageYears}\u5c81 \u00b7 \u4f53\u8102 ${profile.bodyFatPct}% \u00b7 \u7761\u7720\u4e0d\u8db3 ${profile.sleepDebtHours}h \u00b7 \u4f53\u6e29 ${coreTempLabel(profile.coreTempC)} \u00b7 \u5176\u4ed6\u534f\u53d8\u91cf\u6309\u5747\u503c`
      : `${profile.weightKg}kg \u00b7 ${profile.ageYears}\u5c81 \u00b7 \u4f53\u8102 ${profile.bodyFatPct}% \u00b7 \u4f53\u6e29 ${coreTempLabel(profile.coreTempC)} \u00b7 \u5df2\u6309\u4e2a\u4eba\u53c2\u6570\u4fee\u6b63`;
  }
}

function renderJournal() {
  updateKpis();
  const list = $("journalList");
  $("journalCount").textContent = `${state.journal.length} 条`;
  if (!state.journal.length) {
    list.className = "journal-list empty";
    list.textContent = "还没有录入。";
    renderCombinedEffects();
    renderPmi();
    return;
  }
  list.className = "journal-list";
  list.innerHTML = "";
  [...state.journal].sort((a, b) => b.timestamp - a.timestamp).forEach((entry) => {
    const substance = state.substanceById.get(entry.substanceId) || {};
    const params = adjustedPkParams(entry, substance);
    const card = document.createElement("article");
    card.className = "journal-card";
    const time = new Date(entry.timestamp).toLocaleString();
    const ethanolLine = formatEthanolEntry(entry);
    const effectLine = state.advancedMode ? substanceEffectSummary(substance) : consumerSubstanceEffect(substance);
    const metrics = exposureMetricsForEntry(entry, params);
    const warningLine = params.warnings?.length ? params.warnings.join("\u3002") : "";
    card.innerHTML = `
      <header>
        <div class="card-title">${escapeHtml(substanceName(entry.substanceId))}</div>
        <button class="icon-button danger" data-delete-entry="${escapeHtml(entry.id)}" title="删除这条日志">删除</button>
      </header>
      <div class="card-meta">${escapeHtml(time)} · ${entry.dosage} ${escapeHtml(entry.unit)} · ${escapeHtml(routeLabel(entry.route))} · ${escapeHtml(stomachLabel(entry.stomachState))}</div>
      ${ethanolLine ? `<div class="card-note">换算：${escapeHtml(ethanolLine)}</div>` : ""}
      <div class="card-note">${escapeHtml(effectLine)}</div>
      <div class="model-grid">
        <div class="model-chip"><strong>\u4e2a\u4f53</strong> ${params.profile.weightKg}kg / ${params.profile.heightCm}cm / ${params.profile.ageYears}\u5c81 / \u4f53\u8102 ${params.profile.bodyFatPct}%</div>
        <div class="model-chip"><strong>\u534a\u8870\u671f</strong> ${params.baseHalfLifeHours.toFixed(1)}h \u2192 ${params.adjustedHalfLifeHours.toFixed(1)}h</div>
        <div class="model-chip"><strong>ka/ke</strong> ${params.kaPerHour ? params.kaPerHour.toFixed(2) : "\u77ac\u65f6"}/${params.kePerHour.toFixed(2)} h\u207b\u00b9</div>
        <div class="model-chip"><strong>F/Vd</strong> ${params.bioavailabilityFactor.toFixed(2)} / ${params.vdLiters.toFixed(1)}L</div>
        <div class="model-chip"><strong>CL</strong> ${params.adjustedClLPerHour.toFixed(2)} L/h</div>
        <div class="model-chip"><strong>Tlag/Cmax</strong> ${params.tlagHours.toFixed(2)}h / ${formatNumber(metrics.cmax, 3)}</div>
        <div class="model-chip"><strong>AUC24</strong> ${formatNumber(metrics.auc24, 3)}</div>
        <div class="model-chip"><strong>\u534f\u53d8\u91cf</strong> \u7761\u7720 ${params.profile.sleepDebtHours}h / \u4f53\u6e29 ${coreTempLabel(params.profile.coreTempC)} / Q10 ${params.q10Factor.toFixed(2)}</div>
      </div>
      ${warningLine ? `<div class="card-note warning">${escapeHtml(warningLine)}\u3002</div>` : ""}
      ${entry.note ? `<div class="card-note">${escapeHtml(entry.note)}</div>` : ""}
    `;
    list.appendChild(card);
  });
  renderCombinedEffects();
}

async function refreshRisks() {
  const token = ++state.riskRequestToken;
  const entries = activeEntries();
  const ids = [...new Set(entries.map((entry) => entry.substanceId))];
  if (remoteEnabled() && ids.length) {
    try {
      await fetchRemoteDoseRulesForIds(ids);
    } catch (error) {
      setRemoteApiStatus(`\u8fdc\u7a0b\u5242\u91cf\u89c4\u5219\u540c\u6b65\u5931\u8d25\uff1a${error.message || error}`, "error");
    }
  }
  const doseRisks = evaluateDoseRisks();
  const modelRisks = evaluateModelRisks(entries);
  const signalItems = await fetchAdverseSignalsForIds(ids);
  if (entries.length < 2) {
    if (token !== state.riskRequestToken) return;
    state.activeRisks = [...doseRisks, ...modelRisks, ...signalItems]
      .sort((a, b) => riskSortValue(b.risk_level) - riskSortValue(a.risk_level));
    renderRisks();
    return;
  }
  const response = await fetch(`/api/check?ids=${encodeURIComponent(ids.join(","))}`);
  const payload = await response.json();
  const remoteItems = await fetchRemoteInteractionsForIds(ids);
  if (token !== state.riskRequestToken) return;
  state.activeRisks = [...doseRisks, ...modelRisks, ...(payload.items || []), ...remoteItems, ...signalItems]
    .sort((a, b) => riskSortValue(b.risk_level) - riskSortValue(a.risk_level));
  renderRisks();
}

function riskItemsForMode(risks = state.activeRisks || []) {
  const mode = modeProfile();
  if (state.advancedMode) return risks;
  return risks
    .filter((risk) => {
      if (!mode.showUnknownRisks && ["Unknown", "NoKnownClinicalSignificance"].includes(risk.risk_level)) return false;
      return riskSortValue(risk.risk_level) >= mode.minVisibleRiskScore;
    })
    .slice(0, mode.maxRiskCards);
}

function renderRisks() {
  updateKpis();
  const risks = state.activeRisks || [];
  const visibleRisks = riskItemsForMode(risks);
  const list = $("riskList");
  const count = $("riskCount");
  if (count) {
    count.textContent = state.advancedMode
      ? `${risks.length} \u6761`
      : `${visibleRisks.length} \u9879\u9700\u5173\u6ce8`;
  }
  renderCombinedEffects();
  renderPmi();
  renderSideEffectWarning();
  if (!list) return;
  if (!visibleRisks.length) {
    list.className = "risk-list empty";
    list.textContent = state.advancedMode
      ? "\u6682\u65e0\u6d3b\u8dc3\u51b2\u7a81\u6216\u8fc7\u91cf\u98ce\u9669\u3002Unknown \u8868\u793a\u8d44\u6599\u4e0d\u8db3\uff0c\u4e0d\u4ee3\u8868\u5b89\u5168\u3002"
      : "\u6682\u65e0\u9700\u8981\u7acb\u523b\u5904\u7406\u7684\u98ce\u9669\u3002\u82e5\u51fa\u73b0\u660e\u663e\u4e0d\u9002\uff0c\u8bf7\u4f18\u5148\u8054\u7cfb\u533b\u751f\u3001\u836f\u5e08\u6216\u6025\u6551\u3002";
    return;
  }
  list.className = "risk-list";
  list.innerHTML = "";
  visibleRisks.forEach((risk) => list.appendChild(riskCard(risk)));
  if (!state.advancedMode && risks.length > visibleRisks.length) {
    const more = document.createElement("div");
    more.className = "risk-list-hint";
    more.textContent = `\u5df2\u9690\u85cf ${risks.length - visibleRisks.length} \u6761\u4f4e\u4f18\u5148\u7ea7/\u539f\u59cb\u4fe1\u53f7\uff0c\u5207\u6362 ToB \u63a7\u5236\u53f0\u53ef\u67e5\u770b\u5168\u90e8\u6765\u6e90\u4e0e\u660e\u7ec6\u3002`;
    list.appendChild(more);
  }
}

function combinedEffectSignals(substance = {}, effect = "") {
  const text = `${substance.id || ""} ${substance.name_en || ""} ${substance.name_zh || ""} ${substance.category || ""} ${effect || ""} ${(substance.cyp_tags || []).join(" ")}`;
  const signals = [];
  const add = (value) => {
    if (value && !signals.includes(value)) signals.push(value);
  };
  if (substance.category === "Depressant" || /\u9547\u9759|\u6291\u5236|\u50ac\u7720|GABA|\u4e59\u9187|\u9152\u7cbe|ethanol|alcohol/i.test(text)) add("\u4e2d\u67a2\u6291\u5236/\u9547\u9759\u53e0\u52a0");
  if (substance.category === "Stimulant" || /\u5174\u594b|\u5fc3\u7387|\u8840\u538b|\u591a\u5df4\u80fa|\u53bb\u7532\u80be\u4e0a\u817a|stimulant|caffeine|methylphenidate/i.test(text)) add("\u5174\u594b/\u4ea4\u611f\u8d1f\u8377");
  if (/5-HT|SSRI|\u8840\u6e05\u7d20|serotonin|sertraline|tandospirone/i.test(text)) add("5-HT/\u7126\u8651\u901a\u8def");
  if (/CYP3A4.*inhibitor|CYP3A4_?\u6291\u5236|CYP3A4 \u6291\u5236/i.test(text)) add("CYP3A4 \u6291\u5236\u66b4\u9732\u5ef6\u957f");
  if (/CYP1A2|CYP2C9|CYP2C19|CYP2D6|CYP3A4/i.test(text)) add("\u809d\u836f\u9176\u4ee3\u8c22\u901a\u8def\u9700\u5408\u5e76\u67e5\u770b");
  if (/NSAID|COX|\u5e03\u6d1b\u82ac|ibuprofen|\u6297\u708e/i.test(text)) add("NSAID \u80c3\u80a0/\u80be\u810f\u8d1f\u8377");
  return signals;
}

function renderCombinedEffects() {
  const target = $("combinedEffectSummary");
  if (!target) return;
  const entries = activeEntries();
  if (!entries.length) {
    target.className = "combined-effect empty";
    target.textContent = "\u6682\u65e0\u6d3b\u8dc3\u836f\u7269\u3002";
    return;
  }

  const now = Date.now();
  const bySubstance = new Map();
  const rows = entries.map((entry) => {
    const substance = state.substanceById.get(entry.substanceId) || { id: entry.substanceId };
    const params = adjustedPkParams(entry, substance);
    const elapsedHours = minutesBetween(entry.timestamp, now) / 60;
    const exposure = elapsedHours < 0 ? 0 : concentrationAt(elapsedHours, Number(entry.dosage || 0), params);
    const effect = compactSubstanceEffect(substance);
    const existing = bySubstance.get(entry.substanceId) || { substance, count: 0, exposure: 0, effect };
    existing.count += 1;
    existing.exposure += exposure;
    bySubstance.set(entry.substanceId, existing);
    return { entry, substance, params, exposure, effect };
  });

  const activeNames = [...bySubstance.entries()].map(([id, item]) => `${substanceName(id)}${item.count > 1 ? ` \u00d7${item.count}` : ""}`);
  const effectRows = [...bySubstance.entries()].map(([id, item]) => `${substanceName(id)}\uff1a${item.effect}`);
  const signals = [];
  for (const item of bySubstance.values()) {
    combinedEffectSignals(item.substance, item.effect).forEach((signal) => {
      if (!signals.includes(signal)) signals.push(signal);
    });
  }
  const exposureRows = rows
    .filter((row) => row.exposure > 0)
    .sort((a, b) => b.exposure - a.exposure)
    .slice(0, 5)
    .map((row) => `${substanceName(row.entry.substanceId)} ${formatNumber(row.exposure, 3)}`);
  const forecastRows = exposureForecasts(entries, now)
    .slice(0, state.advancedMode ? 5 : 3)
    .map((forecast) => `${forecast.name} ${formatDurationMinutes(forecast.minutesToPeak)}\u540e\u5cf0\u503c ${formatNumber(forecast.peak, forecast.peak < 1 ? 3 : 2)} ${forecast.unit}/L`);
  const forwardIndexRows = forwardExposureGroups(entries, now, 24)
    .slice(0, state.advancedMode ? 5 : 3)
    .map((row) => {
      const unitText = forwardExposureUnitText(row.unit);
      const peakTime = row.minutesToPeak > 0 ? `${formatDurationMinutes(row.minutesToPeak)}\u540e\u8fbe\u5cf0` : "\u5df2\u5728\u9ad8\u4f4d/\u5df2\u8fc7\u5cf0";
      return `${row.name} ${row.index}/100 \u00b7 AUC24 ${formatNumber(row.auc24, row.auc24 < 1 ? 3 : 1)} \u00b7 peak ${formatNumber(row.peak, row.peak < 1 ? 3 : 2)} ${unitText} \u00b7 ${peakTime}`;
    });
  const notableRisks = (state.activeRisks || [])
    .filter((risk) => riskSortValue(risk.risk_level) >= 3)
    .slice(0, 3)
    .map((risk) => `${riskSubjectText(risk)}\uff1a${riskLevelLabel(risk.risk_level)}`);

  target.className = "combined-effect";
  if (!state.advancedMode) {
    target.innerHTML = `
      <div class="combined-head">\u5f53\u524d\u5df2\u670d\u7528\u4f5c\u7528\u6982\u89c8</div>
      <div class="combined-line"><strong>\u6d3b\u8dc3\u9879</strong>${escapeHtml(activeNames.join("\uff1b"))}</div>
      <div class="combined-line"><strong>\u53ef\u80fd\u4f5c\u7528</strong>${escapeHtml(effectRows.join("\uff1b"))}</div>
      <div class="combined-line"><strong>\u53e0\u52a0\u8981\u70b9</strong>${escapeHtml(signals.length ? signals.join("\uff1b") : "\u672a\u8bc6\u522b\u5230\u660e\u786e\u53e0\u52a0\u4fe1\u53f7\uff0c\u4ecd\u8bf7\u4fdd\u5b88\u8ffd\u52a0\u5242\u91cf\u3002")}</div>
      ${forecastRows.length ? `<div class="combined-line warning"><strong>\u5373\u5c06\u8fbe\u5cf0</strong>${escapeHtml(forecastRows.join("\uff1b"))}</div>` : ""}
      ${forwardIndexRows.length ? `<div class="combined-line warning"><strong>\u5411\u540e\u66b4\u9732</strong>${escapeHtml(forwardIndexRows.join("\uff1b"))}</div>` : ""}
      ${notableRisks.length ? `<div class="combined-line warning"><strong>\u4f18\u5148\u770b\u8fd9\u4e9b</strong>${escapeHtml(notableRisks.join("\uff1b"))}</div>` : ""}
    `;
    return;
  }
  target.innerHTML = `
    <div class="combined-head">\u5f53\u524d\u6240\u6709\u5df2\u670d\u7528\u836f\u7269\u7684\u8054\u5408\u4f5c\u7528</div>
    <div class="combined-line"><strong>\u6d3b\u8dc3\u7269\u8d28</strong>${escapeHtml(activeNames.join("\uff1b"))}</div>
    <div class="combined-line"><strong>\u4f5c\u7528\u753b\u50cf</strong>${escapeHtml(effectRows.join("\uff1b"))}</div>
    <div class="combined-line"><strong>\u8054\u5408\u4fe1\u53f7</strong>${escapeHtml(signals.length ? signals.join("\uff1b") : "\u672a\u4ece\u5f53\u524d\u672c\u5730\u6807\u7b7e\u8bc6\u522b\u51fa\u660e\u786e\u53e0\u52a0\u4fe1\u53f7\uff1b\u8fd9\u4e0d\u4ee3\u8868\u5b89\u5168\u3002")}</div>
    <div class="combined-line"><strong>\u6a21\u578b\u5f53\u524d\u66b4\u9732</strong>${escapeHtml(exposureRows.length ? `${exposureRows.join("\uff1b")}\uff08\u76f8\u5bf9\u503c\uff0c\u975e\u771f\u5b9e\u8840\u836f\u6d53\u5ea6\uff09` : "\u5c1a\u672a\u8fdb\u5165\u5f53\u524d\u65f6\u95f4\u70b9\u6216\u6a21\u578b\u66b4\u9732\u63a5\u8fd1 0\u3002")}</div>
    <div class="combined-line"><strong>\u672a\u6765\u5cf0\u503c\u9884\u8b66</strong>${escapeHtml(forecastRows.length ? `${forecastRows.join("\uff1b")}\uff08\u6309\u771f\u5b9e\u7269\u7406\u65f6\u95f4\u524d\u5411\u626b\u63cf\uff09` : "\u672a\u68c0\u51fa\u5c1a\u672a\u8fbe\u5230\u7684\u660e\u663e\u66b4\u9732\u5cf0\u503c\u3002")}</div>
    <div class="combined-line"><strong>\u5411\u540e\u66b4\u9732\u6307\u6570</strong>${escapeHtml(forwardIndexRows.length ? `${forwardIndexRows.join("\uff1b")}\uff08\u672a\u6765 24h \u771f\u5b9e\u7269\u7406\u65f6\u95f4\u626b\u63cf\uff09` : "\u672a\u68c0\u51fa\u672a\u6765 24h \u7684\u660e\u663e\u5269\u4f59\u66b4\u9732\u3002")}</div>
    ${notableRisks.length ? `<div class="combined-line warning"><strong>\u9ad8\u4f18\u5148\u7ea7\u63d0\u9192</strong>${escapeHtml(notableRisks.join("\uff1b"))}</div>` : ""}
  `;
}

function clampFactor(value, min, max) {
  const num = Number(value);
  if (!Number.isFinite(num)) return min;
  return Math.min(Math.max(num, min), max);
}

function substanceText(substance = {}) {
  return `${substance.id || ""} ${substance.name_en || ""} ${substance.name_zh || ""} ${substance.category || ""} ${substance.solubility || ""} ${(substance.cyp_tags || []).join(" ")} ${substance.identifiers?.aliases || ""}`.toLowerCase();
}

function isLipophilicSubstance(substance = {}) {
  const text = substanceText(substance);
  return String(substance.solubility || "").toLowerCase().includes("lipo") || /benzodiazepine|lipophilic|zolpidem|lorazepam|diazepam/.test(text);
}

function childPughClass(score) {
  if (score <= 6) return "A";
  if (score <= 9) return "B";
  return "C";
}

function childPughClearanceFactor(score) {
  const value = clampNumber(score, 5, 5, 15);
  if (value <= 6) return clampFactor(1 - (value - 5) * 0.05, 0.9, 1);
  if (value <= 9) return clampFactor(0.9 - (value - 6) * (0.25 / 3), 0.65, 0.9);
  return clampFactor(0.65 - (value - 9) * (0.3 / 6), 0.35, 0.65);
}

function doseInMg(entry = {}) {
  const dose = Number(entry.dosage || 0);
  if (!Number.isFinite(dose) || dose <= 0) return 0;
  const unit = String(entry.unit || "mg").toLowerCase();
  if (unit === "mg") return dose;
  if (unit === "g") return dose * 1000;
  if (unit === "ug" || unit === "mcg") return dose / 1000;
  return 0;
}

function dispositionWeights(substance = {}, isLipophilic = false) {
  const text = substanceText(substance);
  const hasCyp = /cyp\d|cyp/.test(text);
  let renalWeight = isLipophilic ? 0.25 : 0.58;
  if (hasCyp) renalWeight = Math.min(renalWeight, 0.28);
  if (/renal|kidney|\u80be\u6392\u6cc4|\u4eb2\u6c34/.test(text)) renalWeight = Math.max(renalWeight, 0.65);
  const hepaticWeight = 1 - renalWeight;
  return { hepaticWeight, renalWeight, hasCyp };
}

function pgxClearanceFactor(profile, substance, weights) {
  const phenotype = metabolicProfiles[profile.metabolicType] || metabolicProfiles.EM;
  const activityScore = Number(phenotype.activityScore || 1.75);
  const normalized = clampFactor(activityScore / 1.75, 0.2, 1.75);
  const pgxWeight = weights.hasCyp ? 0.75 : 0.25;
  return {
    activityScore,
    pgxWeight,
    factor: clampFactor(1 + (normalized - 1) * pgxWeight, 0.35, 1.65),
  };
}

function renalClearanceFactor(profile, renalTheta = 0.85) {
  const eGfr = clampNumber(profile.eGfr, 120, 5, 220);
  const hydration = hydrationProfiles[profile.hydrationState] || hydrationProfiles.Normal;
  const critical = criticalStateProfiles[profile.criticalState] || criticalStateProfiles.Stable;
  const egfrFactor = Math.pow(eGfr / 120, renalTheta);
  return clampFactor(egfrFactor * hydration.renal * critical.renal, 0.08, 1.85);
}

function dynamicClearanceFactor(profile, substance = {}) {
  const temp = clampNumber(profile.coreTempC, 37, 32, 43);
  const q10Temp = Math.min(temp, 40.5);
  const q10Factor = clampFactor(Math.pow(2, (q10Temp - 37) / 10), 0.72, 1.25);
  const enzymeStabilityFactor = temp > 40.5 ? 0.72 : 1;
  const hr = clampNumber(profile.heartRateBpm, 70, 35, 220);
  const highHrPenalty = hr > 115 ? 1 - (hr - 115) / 360 : 1;
  const lowHrPenalty = hr < 50 ? 0.9 : 1;
  const heartRateFactor = clampFactor(highHrPenalty * lowHrPenalty, 0.72, 1.05);
  const sleepDebt = clampNumber(profile.sleepDebtHours, 0, 0, 72);
  const sleepFactor = clampFactor(1 - sleepDebt * 0.0125, 0.72, 1);
  const critical = criticalStateProfiles[profile.criticalState] || criticalStateProfiles.Stable;
  const factor = clampFactor(q10Factor * enzymeStabilityFactor * heartRateFactor * sleepFactor * critical.cl, 0.25, 1.65);
  return { factor, q10Factor, enzymeStabilityFactor, heartRateFactor, sleepFactor, criticalFactor: critical.cl };
}

function absorptionCovariates(entry, substance, profile, isLipophilic) {
  const route = routeProfiles[entry.route] || routeProfiles.Other;
  const stomach = stomachProfiles[entry.stomachState] || stomachProfiles.Light;
  const temp = clampNumber(profile.coreTempC, 37, 32, 43);
  const hr = clampNumber(profile.heartRateBpm, 70, 35, 220);
  const sleepDebt = clampNumber(profile.sleepDebtHours, 0, 0, 72);
  const oral = entry.route === "Oral";
  let tlagHours = 0;
  if (oral) {
    tlagHours = { Fasting: 0, Light: 0.25, Heavy: 0.75 }[entry.stomachState] ?? 0.25;
  }
  if (oral) tlagHours += Math.min(0.65, sleepDebt * 0.025);
  const sleepAbsorptionFactor = oral ? clampFactor(1 - sleepDebt * 0.02, 0.62, 1) : 1;
  let kaFactor = route.ka * (oral ? stomach.ka : 1) * sleepAbsorptionFactor;
  let bioavailabilityFactor = route.f * (oral ? stomach.f : 1);
  if (entry.stomachState === "Heavy") bioavailabilityFactor *= isLipophilic ? 1.12 : 1.03;
  if (entry.route === "Topical") {
    const thermalFlux = clampFactor(Math.pow(2, (Math.min(temp, 40) - 37) / 10), 0.75, 1.35);
    const perfusionFlux = clampFactor(1 + Math.max(0, hr - 80) / 260, 1, 1.45);
    kaFactor *= thermalFlux * perfusionFlux;
    tlagHours += 0.5;
  }
  return {
    tlagHours,
    absorptionFactor: clampFactor(kaFactor, 0.03, 12),
    bioavailabilityFactor: clampFactor(bioavailabilityFactor, 0.02, 2.0),
  };
}

function nonlinearWarnings(entry, substance, params) {
  const warnings = [];
  const text = substanceText(substance);
  const doseMgKg = doseInMg(entry) / Math.max(params.profile.weightKg || 70, 1);
  if (params.modelType === "ethanol_zero_order_widmark") {
    const gramsPerKg = Number(entry.ethanol?.grams || (String(entry.unit).toLowerCase() === "g" ? entry.dosage : 0)) / Math.max(params.profile.weightKg || 70, 1);
    if (gramsPerKg >= 0.6) warnings.push("\u4e59\u9187\u5df2\u6309\u8fd1\u4f3c\u96f6\u7ea7\u6d88\u9664\u5904\u7406\uff1b\u9ad8\u5242\u91cf\u4e0b\u6e05\u9664\u4e0d\u518d\u968f\u6d53\u5ea6\u7b49\u6bd4\u589e\u52a0\u3002");
  }
  if (/phenytoin|\u82ef\u59a5\u82f1|theophylline|\u8336\u78b1|salicylate/.test(text)) {
    warnings.push("\u5df2\u8bc6\u522b\u5bb9\u91cf\u9650\u5236/\u7c73\u6c0f\u52a8\u529b\u5b66\u5019\u9009\u7269\u8d28\uff1b\u7f3a\u5c11 Km/Vmax \u65f6\u4ec5\u8fdb\u884c\u975e\u7ebf\u6027\u84c4\u79ef\u9884\u8b66\u3002");
  }
  if (doseMgKg >= 20 && params.modelType !== "ethanol_zero_order_widmark") {
    warnings.push("\u5355\u6b21 mg/kg \u8d1f\u8377\u8f83\u9ad8\uff0c\u4e00\u7ea7\u6d88\u9664\u53ef\u80fd\u4f4e\u4f30\u84c4\u79ef\u6216\u6bd2\u6027\u98ce\u9669\u3002");
  }
  if (params.profile.eGfr < 30) warnings.push("eGFR < 30\uff1a\u4eb2\u6c34/\u80be\u6392\u6cc4\u7269\u8d28\u7684\u84c4\u79ef\u98ce\u9669\u4e0a\u5347\u3002");
  if (params.profile.childPughScore >= 10) warnings.push("Child-Pugh C\uff1a\u809d\u6e05\u9664\u663e\u8457\u964d\u989d\uff0c\u53ef\u80fd\u5ef6\u957f\u66b4\u9732\u3002");
  if (params.profile.coreTempC > 40.5) warnings.push("\u9ad8\u70ed\u8d85\u8fc7 Q10 \u7a33\u5b9a\u5916\u63a8\u8303\u56f4\uff0c\u5df2\u5207\u6362\u4e3a\u9176\u7a33\u5b9a\u6027\u98ce\u9669\u72b6\u6001\u3002");
  if (params.profile.heartRateBpm >= 140) warnings.push("\u9ad8\u5fc3\u7387\u533a\u95f4\uff1a\u5df2\u4e0b\u8c03\u809d/\u80be\u6e05\u9664\u56e0\u5b50\uff0c\u540c\u65f6\u63d0\u793a Cmax/AUC \u8d85\u9650\u98ce\u9669\u3002");
  return warnings;
}

function adjustedPkParams(entry, substance = {}) {
  const profileInput = getProfileFromInputs();
  const profile = {
    weightKg: Math.max(Number(profileInput.weightKg || 70), 25),
    heightCm: Math.max(Number(profileInput.heightCm || 170), 120),
    bodyFatPct: Math.min(Math.max(Number(profileInput.bodyFatPct || 20), 3), 70),
    ageYears: clampNumber(profileInput.ageYears, 35, 0, 110),
    eGfr: 120,
    childPughScore: 5,
    heartRateBpm: 70,
    coreTempC: normalizeCoreTemp(profileInput.coreTempC),
    sleepDebtHours: clampNumber(profileInput.sleepDebtHours, 0, 0, 72),
    metabolicType: "EM",
    hydrationState: "Normal",
    criticalState: "Stable",
  };
  const route = routeProfiles[entry.route] || routeProfiles.Other;
  const weightKg = profile.weightKg;
  const weightRatio = weightKg / 70;
  const bmi = weightKg / Math.pow(profile.heightCm / 100, 2);
  const lbmKg = weightKg * (1 - profile.bodyFatPct / 100);
  const fatMassKg = Math.max(weightKg - lbmKg, 0);
  const totalBodyWaterLiters = Math.max(12, lbmKg * 0.73 + fatMassKg * 0.1);
  const baseHalfLifeHours = Math.max(Number(substance?.base_half_life || 4), 0.25);
  const isEthanol = isEthanolSubstance(substance);
  const isLipophilic = isLipophilicSubstance(substance);
  const weights = dispositionWeights(substance, isLipophilic);
  const hydration = hydrationProfiles[profile.hydrationState] || hydrationProfiles.Normal;
  const critical = criticalStateProfiles[profile.criticalState] || criticalStateProfiles.Stable;

  const thetaVdLiters = isEthanol ? 42 : isLipophilic ? 84 : 42;
  const expectedTbwLiters = Math.max(15, weightKg * 0.6);
  const bodyCompositionFactor = isLipophilic
    ? clampFactor(1 + (profile.bodyFatPct - 20) / 100, 0.65, 1.55)
    : clampFactor(totalBodyWaterLiters / expectedTbwLiters, 0.55, 1.45);
  const criticalVdFactor = isLipophilic ? 1 : critical.vdHydrophilic;
  const vdLiters = isEthanol
    ? Math.max(8, totalBodyWaterLiters * hydration.vd)
    : Math.max(3, thetaVdLiters * Math.pow(weightRatio, 1.0) * bodyCompositionFactor * hydration.vd * criticalVdFactor);

  const baseKePerHour = Math.log(2) / baseHalfLifeHours;
  const baseClLPerHour = baseKePerHour * thetaVdLiters;
  const maturityFactor = profile.ageYears >= 16 ? 1 : clampFactor(profile.ageYears / (profile.ageYears + 2), 0.18, 0.95);
  const ageFrailtyFactor = profile.ageYears > 75 ? clampFactor(1 - (profile.ageYears - 75) * 0.01, 0.72, 1) : 1;
  const allometricClFactor = Math.pow(weightRatio, 0.75) * maturityFactor * ageFrailtyFactor;
  const pgx = pgxClearanceFactor(profile, substance, weights);
  const hepaticFactor = childPughClearanceFactor(profile.childPughScore);
  const renalFactor = renalClearanceFactor(profile);
  const organFactor = clampFactor(weights.hepaticWeight * hepaticFactor + weights.renalWeight * renalFactor, 0.08, 1.8);
  const dynamic = dynamicClearanceFactor(profile, substance);
  const adjustedClLPerHour = Math.max(0.01, baseClLPerHour * allometricClFactor * pgx.factor * organFactor * dynamic.factor);
  const kePerHour = Math.max(adjustedClLPerHour / Math.max(vdLiters, 0.1), 0.001);
  const adjustedHalfLifeHours = Math.log(2) / kePerHour;

  const absorption = absorptionCovariates(entry, substance, profile, isLipophilic);
  const onset = Math.max(Number(substance?.base_onset || 30), 1);
  const kaPerHour = route.instant ? null : (Math.log(2) / Math.max(onset / 60, 0.15)) * absorption.absorptionFactor;
  const firstPassFactor = entry.route === "Oral" && weights.hepaticWeight > 0.5 ? clampFactor(1 + (1 - hepaticFactor) * 0.25, 1, 1.25) : 1;
  const bioavailabilityFactor = clampFactor(absorption.bioavailabilityFactor * firstPassFactor, 0.02, 2.2);

  const params = {
    profile: { ...profile, bmi: Number(bmi.toFixed(1)), lbmKg: Number(lbmKg.toFixed(1)) },
    modelType: isEthanol ? "ethanol_zero_order_widmark" : route.instant ? "instant_elimination" : "one_compartment_first_order_absorption",
    baseHalfLifeHours,
    adjustedHalfLifeHours,
    baseClLPerHour,
    adjustedClLPerHour,
    allometricClFactor,
    pgxActivityScore: pgx.activityScore,
    pgxFactor: pgx.factor,
    pgxWeight: pgx.pgxWeight,
    hepaticWeight: weights.hepaticWeight,
    renalWeight: weights.renalWeight,
    hepaticFactor,
    renalFactor,
    organFactor,
    dynamicFactor: dynamic.factor,
    q10Factor: dynamic.q10Factor,
    enzymeStabilityFactor: dynamic.enzymeStabilityFactor,
    heartRateFactor: dynamic.heartRateFactor,
    sleepFactor: dynamic.sleepFactor,
    criticalFactor: dynamic.criticalFactor,
    childPughClass: childPughClass(profile.childPughScore),
    tlagHours: absorption.tlagHours,
    absorptionFactor: absorption.absorptionFactor,
    bioavailabilityFactor,
    bodyCompositionFactor,
    totalBodyWaterLiters,
    ethanolEliminationGLPerHour: 0.15 * clampFactor(dynamic.factor, 0.55, 1.25),
    vdLiters,
    kaPerHour,
    kePerHour,
    exposureFactor: bioavailabilityFactor / vdLiters,
  };
  params.warnings = nonlinearWarnings(entry, substance, params);
  return params;
}

function concentrationAt(tHours, dose, params) {
  const laggedHours = tHours - Number(params.tlagHours || 0);
  if (laggedHours < 0) return 0;
  const amount = Math.max(Number(dose || 0), 0) * params.bioavailabilityFactor;
  const vd = Math.max(params.vdLiters, 1);
  if (params.modelType === "ethanol_zero_order_widmark") {
    const ka = Math.max(params.kaPerHour || 1.4, 0.15);
    const absorptionHours = params.kaPerHour ? 1 / ka : 0.5;
    const absorbedFraction = params.kaPerHour ? 1 - Math.exp(-ka * Math.max(laggedHours, 0)) : 1;
    const peakGL = (amount / vd) * absorbedFraction;
    const eliminationStarted = Math.max(laggedHours - absorptionHours, 0);
    return Math.max(peakGL - params.ethanolEliminationGLPerHour * eliminationStarted, 0);
  }
  const ke = Math.max(params.kePerHour, 0.001);
  if (params.modelType === "instant_elimination" || !params.kaPerHour) {
    return (amount / vd) * Math.exp(-ke * laggedHours);
  }
  let ka = Math.max(params.kaPerHour, 0.001);
  if (Math.abs(ka - ke) < 0.001) ka += 0.001;
  const value = (amount * ka) / (vd * (ka - ke)) * (Math.exp(-ke * laggedHours) - Math.exp(-ka * laggedHours));
  return Math.max(value, 0);
}

function exposureMetricsForEntry(entry, params, horizonHours = 24) {
  const samples = 144;
  let auc = 0;
  let previous = concentrationAt(0, entry.dosage, params);
  let cmax = previous;
  let tmax = 0;
  for (let i = 1; i <= samples; i += 1) {
    const t = horizonHours * (i / samples);
    const value = concentrationAt(t, entry.dosage, params);
    auc += ((previous + value) / 2) * (horizonHours / samples);
    if (value > cmax) {
      cmax = value;
      tmax = t;
    }
    previous = value;
  }
  return { auc24: auc, cmax, tmaxHours: tmax };
}

function popPkExplanation(params) {
  const pieces = [
    `CL ${(params.adjustedClLPerHour || 0).toFixed(2)} L/h`,
    `Vd ${(params.vdLiters || 0).toFixed(1)} L`,
    `AS ${(params.pgxActivityScore || 0).toFixed(2)}(\u5747\u503c)`,
    `\u4f53\u6e29 ${coreTempLabel(params.profile.coreTempC)}`,
    `\u7761\u7720\u4e0d\u8db3 ${params.profile.sleepDebtHours || 0}h`,
    `Q10 ${(params.q10Factor || 1).toFixed(2)}`,
  ];
  return pieces.join(" \u00b7 ");
}

function syncCanvasSize(canvas) {
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const width = Math.max(320, Math.round((rect.width || canvas.clientWidth || 1100) * dpr));
  const height = Math.max(220, Math.round((rect.height || canvas.clientHeight || 460) * dpr));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  return { width, height, dpr };
}

function roundRect(ctx, x, y, width, height, radius) {
  const r = Math.min(radius, width / 2, height / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + width - r, y);
  ctx.quadraticCurveTo(x + width, y, x + width, y + r);
  ctx.lineTo(x + width, y + height - r);
  ctx.quadraticCurveTo(x + width, y + height, x + width - r, y + height);
  ctx.lineTo(x + r, y + height);
  ctx.quadraticCurveTo(x, y + height, x, y + height - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

function loadCurveZoom() {
  state.curveZoom = clampNumber(localStorage.getItem(curveZoomStorageKey), 1, 0.25, 8);
  state.curvePanMinutes = clampNumber(localStorage.getItem(curvePanStorageKey), 0, -100000, 100000);
  updateCurveZoomControls();
}

function requestCurveDraw() {
  requestAnimationFrame(drawCurve);
}

function setCurveZoom(value) {
  state.curveZoom = clampNumber(value, 1, 0.25, 8);
  localStorage.setItem(curveZoomStorageKey, String(state.curveZoom));
  updateCurveZoomControls();
  requestCurveDraw();
}

function setCurvePan(minutes) {
  state.curvePanMinutes = clampNumber(minutes, 0, -100000, 100000);
  localStorage.setItem(curvePanStorageKey, String(state.curvePanMinutes));
  updateCurveZoomControls();
  requestCurveDraw();
}

function zoomCurve(multiplier) {
  setCurveZoom(state.curveZoom * multiplier);
}

function panCurveByMinutes(minutes) {
  setCurvePan(state.curvePanMinutes + Number(minutes || 0));
}

function panCurveByFraction(fraction) {
  const viewport = curveViewport(activeEntries(), Date.now());
  panCurveByMinutes(viewport.horizonMinutes * Number(fraction || 0));
}

function resetCurveView() {
  state.curveZoom = 1;
  state.curvePanMinutes = 0;
  localStorage.setItem(curveZoomStorageKey, String(state.curveZoom));
  localStorage.setItem(curvePanStorageKey, String(state.curvePanMinutes));
  updateCurveZoomControls();
  requestCurveDraw();
}

function formatDurationMinutes(minutes) {
  const value = Math.max(1, Number(minutes || 0));
  if (value < 120) return `${Math.round(value)}min`;
  if (value < 48 * 60) return `${formatNumber(value / 60, value < 600 ? 1 : 0)}h`;
  return `${formatNumber(value / 1440, 1)}d`;
}

function curveViewport(entries, now) {
  const futureMinutes = 12 * 60;
  const minTimestamp = entries.length ? Math.min(...entries.map((entry) => entry.timestamp)) : now;
  const defaultStart = entries.length ? Math.min(minTimestamp, now) : now;
  const defaultPast = Math.max(0, minutesBetween(defaultStart, now));
  const defaultHorizon = Math.max(futureMinutes, defaultPast + futureMinutes);
  const zoom = clampNumber(state.curveZoom, 1, 0.25, 8);
  let startTimestamp;
  let pastMinutes;
  let horizonMinutes;
  if (Math.abs(zoom - 1) < 0.001) {
    startTimestamp = defaultStart;
    pastMinutes = defaultPast;
    horizonMinutes = defaultHorizon;
  } else {
    horizonMinutes = Math.max(30, defaultHorizon / zoom);
    pastMinutes = Math.max(5, Math.min(horizonMinutes - 5, horizonMinutes * 0.35));
    startTimestamp = now - pastMinutes * 60000;
  }
  const panMinutes = clampNumber(state.curvePanMinutes, 0, -100000, 100000);
  if (Math.abs(panMinutes) > 0.01) {
    startTimestamp += panMinutes * 60000;
    pastMinutes = minutesBetween(startTimestamp, now);
  }
  return { startTimestamp, pastMinutes, horizonMinutes, panMinutes };
}

function formatSignedDurationMinutes(minutes) {
  const value = Number(minutes || 0);
  if (Math.abs(value) < 1) return "\u5c45\u4e2d";
  return `${value > 0 ? "+" : "-"}${formatDurationMinutes(Math.abs(value))}`;
}

function updateCurveZoomControls(viewport = null) {
  const slider = $("curveZoomSlider");
  const label = $("curveZoomLabel");
  if (slider) slider.value = String(state.curveZoom);
  if (label) {
    const horizon = viewport?.horizonMinutes;
    let windowText = "时间窗";
    if (horizon && viewport?.startTimestamp) {
      const endTimestamp = viewport.startTimestamp + horizon * 60000;
      const startLabel = formatAxisTime(viewport.startTimestamp, viewport.startTimestamp, endTimestamp);
      const endLabel = formatAxisTime(endTimestamp, viewport.startTimestamp, endTimestamp);
      const startText = `${startLabel.date ? `${startLabel.date} ` : ""}${startLabel.time}`;
      const endText = `${endLabel.date ? `${endLabel.date} ` : ""}${endLabel.time}`;
      windowText = `${startText}-${endText} / ${formatDurationMinutes(horizon)}`;
    }
    label.textContent = `${state.curveZoom.toFixed(2)}x · ${windowText} · 平移 ${formatSignedDurationMinutes(state.curvePanMinutes)}`;
  }
}

function drawCurve() {
  const canvas = $("curveCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const { width, height, dpr } = syncCanvasSize(canvas);
  const left = 56 * dpr;
  const right = 12 * dpr;
  const top = 34 * dpr;
  const bottom = 54 * dpr;
  const plotWidth = Math.max(1, width - left - right);
  const plotHeight = Math.max(1, height - top - bottom);

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);

  const now = Date.now();
  const entries = activeEntries();
  const viewport = curveViewport(entries, now);
  const { startTimestamp, pastMinutes, horizonMinutes } = viewport;
  updateCurveZoomControls(viewport);
  const samples = 260;
  const unitLabel = (entry) => {
    const unit = String(entry?.unit || "mg").toLowerCase();
    if (unit === "mcg") return "ug";
    return unit || "mg";
  };
  const formatConcentration = (value, unit) => {
    const digits = value < 1 ? 3 : value < 10 ? 2 : 1;
    return `${formatNumber(value, digits)} ${unit === "mixed" ? "混合单位/L" : `${unit}/L`}`;
  };
  const allSeries = entries.map((entry, index) => {
    const substance = state.substanceById.get(entry.substanceId) || {};
    const params = adjustedPkParams(entry, substance);
    const dose = Number(entry.dosage || 1);
    const nowHours = minutesBetween(entry.timestamp, now) / 60;
    const currentValue = nowHours >= 0 ? concentrationAt(nowHours, dose, params) : 0;
    const values = [];
    for (let i = 0; i <= samples; i += 1) {
      const axisMinutes = horizonMinutes * (i / samples);
      const axisTimestamp = startTimestamp + axisMinutes * 60000;
      const tHours = minutesBetween(entry.timestamp, axisTimestamp) / 60;
      const value = tHours < 0 ? 0 : concentrationAt(tHours, dose, params);
      values.push(value);
    }
    return {
      id: entry.substanceId,
      entry,
      params,
      values,
      currentValue,
      unit: unitLabel(entry),
      color: colors[index % colors.length],
    };
  });

  const activeIds = [...new Set(allSeries.map((series) => series.id))];
  [...state.curveHiddenSubstances].forEach((id) => {
    if (!activeIds.includes(id)) state.curveHiddenSubstances.delete(id);
  });
  if (activeIds.length && activeIds.every((id) => state.curveHiddenSubstances.has(id))) {
    state.curveHiddenSubstances.clear();
  }

  const groupedMap = new Map();
  allSeries.forEach((series) => {
    let group = groupedMap.get(series.id);
    if (!group) {
      group = {
        id: series.id,
        name: substanceName(series.id),
        color: series.color,
        values: Array(samples + 1).fill(0),
        unitSet: new Set(),
        currentValue: 0,
        count: 0,
        halfLives: [],
      };
      groupedMap.set(series.id, group);
    }
    group.count += 1;
    group.currentValue += series.currentValue || 0;
    group.unitSet.add(series.unit);
    group.halfLives.push(series.params.adjustedHalfLifeHours);
    series.values.forEach((value, index) => {
      group.values[index] += value || 0;
    });
  });
  const groupedSeries = [...groupedMap.values()].map((group) => ({
    ...group,
    unit: group.unitSet.size === 1 ? [...group.unitSet][0] : "mixed",
    halfLife: group.halfLives.reduce((sum, value) => sum + value, 0) / Math.max(group.halfLives.length, 1),
  }));
  const visibleGroups = groupedSeries.filter((group) => !state.curveHiddenSubstances.has(group.id));
  const totalCurrentValue = visibleGroups.reduce((sum, group) => sum + (group.currentValue || 0), 0);
  const totalValues = Array.from({ length: samples + 1 }, (_, i) => visibleGroups.reduce((sum, group) => sum + (group.values[i] || 0), 0));
  const rawMax = Math.max(1, ...totalValues, ...visibleGroups.flatMap((group) => group.values));
  const magnitude = 10 ** Math.floor(Math.log10(rawMax));
  const normalized = rawMax / magnitude;
  const step = normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  const maxValue = step * magnitude;
  const visibleUnits = new Set(visibleGroups.map((group) => group.unit));
  const singleVisibleUnit = visibleUnits.size === 1 ? [...visibleUnits][0] : null;
  const yAxisLabel = singleVisibleUnit && singleVisibleUnit !== "mixed" ? `浓度 (${singleVisibleUnit}/L)` : "浓度/相对负荷";
  const chartTopLegendText = $("chartTopLegendText");
  if (chartTopLegendText) {
    chartTopLegendText.textContent = singleVisibleUnit && singleVisibleUnit !== "mixed"
      ? `总浓度 + 单药浓度 (${singleVisibleUnit}/L)`
      : "总负荷 + 各药物浓度";
  }

  ctx.lineWidth = 1 * dpr;
  ctx.strokeStyle = "#e8eef5";
  ctx.fillStyle = "#5f6b7a";
  ctx.font = `${12 * dpr}px Segoe UI, Microsoft YaHei, sans-serif`;
  ctx.textBaseline = "middle";
  ctx.textAlign = "right";
  const yTicks = 10;
  for (let i = 0; i <= yTicks; i += 1) {
    const ratio = i / yTicks;
    const y = top + plotHeight * ratio;
    ctx.beginPath();
    ctx.moveTo(left, y);
    ctx.lineTo(left + plotWidth, y);
    ctx.stroke();
    const value = maxValue * (1 - ratio);
    ctx.fillText(formatNumber(value, value < 10 ? 1 : 0), left - 10 * dpr, y);
  }

  ctx.strokeStyle = "#d6dee8";
  ctx.beginPath();
  ctx.moveTo(left, top);
  ctx.lineTo(left, top + plotHeight);
  ctx.lineTo(left + plotWidth, top + plotHeight);
  ctx.stroke();

  ctx.fillStyle = "#5f6b7a";
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  const xTicks = 10;
  const viewportEndTimestamp = startTimestamp + horizonMinutes * 60000;
  for (let i = 0; i <= xTicks; i += 1) {
    const ratio = i / xTicks;
    const x = left + plotWidth * ratio;
    const tickTimestamp = startTimestamp + horizonMinutes * ratio * 60000;
    const label = formatAxisTime(tickTimestamp, startTimestamp, viewportEndTimestamp);
    ctx.fillText(label.time, x, top + plotHeight + 8 * dpr);
    if (label.date) {
      ctx.fillText(label.date, x, top + plotHeight + 23 * dpr);
    }
  }
  ctx.fillStyle = "#50627a";
  ctx.fillText("真实时间", left + plotWidth / 2, height - 18 * dpr);
  ctx.save();
  ctx.translate(14 * dpr, top + plotHeight / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.textBaseline = "middle";
  ctx.fillText(yAxisLabel, 0, 0);
  ctx.restore();

  const xForIndex = (i) => left + plotWidth * (i / samples);
  const yForValue = (value) => top + plotHeight * (1 - Math.max(0, Math.min(value / maxValue, 1)));
  const hasCurveHover = state.curveHoverRatio != null;
  const currentRatio = horizonMinutes > 0 ? Math.max(0, Math.min(1, pastMinutes / horizonMinutes)) : 0;
  const hoverIndex = hasCurveHover
    ? Math.max(0, Math.min(samples, Math.round(state.curveHoverRatio * samples)))
    : Math.max(0, Math.min(samples, Math.round(currentRatio * samples)));

  if (visibleGroups.length && totalValues.some((value) => value > 0)) {
    ctx.beginPath();
    totalValues.forEach((value, i) => {
      const x = xForIndex(i);
      const y = yForValue(value);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.lineTo(left + plotWidth, top + plotHeight);
    ctx.lineTo(left, top + plotHeight);
    ctx.closePath();
    ctx.fillStyle = "rgba(38, 173, 231, 0.18)";
    ctx.fill();

    ctx.strokeStyle = "#16a5e8";
    ctx.lineWidth = 2.5 * dpr;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.beginPath();
    totalValues.forEach((value, i) => {
      const x = xForIndex(i);
      const y = yForValue(value);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    visibleGroups.forEach((group) => {
      ctx.strokeStyle = group.color;
      ctx.globalAlpha = visibleGroups.length === 1 ? 0.95 : 0.72;
      ctx.lineWidth = (visibleGroups.length === 1 ? 2.5 : 1.8) * dpr;
      ctx.beginPath();
      group.values.forEach((value, i) => {
        const x = xForIndex(i);
        const y = yForValue(value);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    });
    ctx.globalAlpha = 1;

    if (hasCurveHover) {
      const markerX = xForIndex(hoverIndex);
      const markerY = yForValue(totalValues[hoverIndex]);
      const axisTimestamp = startTimestamp + horizonMinutes * (hoverIndex / samples) * 60000;
      ctx.fillStyle = "#ffffff";
      ctx.strokeStyle = "#16a5e8";
      ctx.lineWidth = 2 * dpr;
      ctx.beginPath();
      ctx.arc(markerX, markerY, 6 * dpr, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
  
      const drugRows = visibleGroups
        .map((group) => ({ ...group, current: group.values[hoverIndex] || 0 }))
        .sort((a, b) => b.current - a.current)
        .slice(0, 6);
      const tooltipLines = [
        { text: `时间: ${formatTooltipTime(axisTimestamp)}`, color: "#ffffff" },
        { text: singleVisibleUnit && singleVisibleUnit !== "mixed" ? `总浓度: ${formatConcentration(totalValues[hoverIndex] || 0, singleVisibleUnit)}` : `总负荷: ${formatNumber(totalValues[hoverIndex] || 0, 3)}`, color: "#16a5e8" },
        ...drugRows.map((group) => ({ text: `${group.name}: ${formatConcentration(group.current, group.unit)}`, color: group.color })),
      ];
      if (visibleGroups.length > drugRows.length) {
        tooltipLines.push({ text: `其余 ${visibleGroups.length - drugRows.length} 个药物已省略`, color: "#ffffff" });
      }
      const tooltipW = Math.min(360 * dpr, width - left - 12 * dpr);
      const tooltipH = (18 + tooltipLines.length * 19) * dpr;
      const tooltipX = Math.min(Math.max(markerX + 10 * dpr, left), width - tooltipW - 8 * dpr);
      const tooltipY = Math.min(Math.max(top + 6 * dpr, markerY - tooltipH - 10 * dpr), top + plotHeight - tooltipH - 4 * dpr);
      ctx.fillStyle = "#202a3a";
      roundRect(ctx, tooltipX, tooltipY, tooltipW, tooltipH, 6 * dpr);
      ctx.fill();
      ctx.font = `${12 * dpr}px Segoe UI, Microsoft YaHei, sans-serif`;
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      tooltipLines.forEach((line, index) => {
        const y = tooltipY + (10 + index * 19) * dpr;
        if (index >= 1) {
          ctx.fillStyle = line.color;
          ctx.fillRect(tooltipX + 12 * dpr, y + 2 * dpr, 10 * dpr, 10 * dpr);
          ctx.fillStyle = "#ffffff";
          ctx.fillText(line.text, tooltipX + 28 * dpr, y, tooltipW - 36 * dpr);
        } else {
          ctx.fillStyle = "#ffffff";
          ctx.fillText(line.text, tooltipX + 12 * dpr, y);
        }
      });
    }
  }

  const nowX = left + plotWidth * Math.min(Math.max(pastMinutes / horizonMinutes, 0), 1);
  if (nowX >= left && nowX <= left + plotWidth) {
    ctx.strokeStyle = "rgba(37, 99, 235, 0.28)";
    ctx.setLineDash([4 * dpr, 4 * dpr]);
    ctx.beginPath();
    ctx.moveTo(nowX, top);
    ctx.lineTo(nowX, top + plotHeight);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  const legend = $("legend");
  if (!legend) return;
  legend.innerHTML = "";
  if (!groupedSeries.length) {
    const empty = document.createElement("div");
    empty.className = "legend-item";
    empty.textContent = "暂无活跃曲线；新增日志后会按体重、体脂、年龄、睡眠、体温、途径和胃部状态估算。";
    legend.appendChild(empty);
    return;
  }
  const allButton = document.createElement("button");
  allButton.type = "button";
  allButton.className = `legend-item curve-filter all ${state.curveHiddenSubstances.size ? "" : "active"}`;
  allButton.dataset.curveFilter = "all";
  allButton.setAttribute("aria-pressed", state.curveHiddenSubstances.size ? "false" : "true");
  allButton.title = "显示全部药物曲线";
  allButton.innerHTML = `<span class="swatch total-swatch"></span>全部 · 总曲线 · 当前 ${singleVisibleUnit && singleVisibleUnit !== "mixed" ? formatConcentration(totalCurrentValue, singleVisibleUnit) : `总负荷 ${formatNumber(totalCurrentValue, 3)}`}`;
  legend.appendChild(allButton);
  groupedSeries.forEach((group) => {
    const hidden = state.curveHiddenSubstances.has(group.id);
    const current = group.currentValue || 0;
    const item = document.createElement("button");
    item.type = "button";
    item.className = `legend-item curve-filter ${hidden ? "muted" : "active"}`;
    item.dataset.curveSubstance = group.id;
    item.setAttribute("aria-pressed", hidden ? "false" : "true");
    item.title = "点击单独查看该药物；Ctrl/Command 点击可多选显示或隐藏";
    item.innerHTML = `<span class="swatch" style="background:${group.color}"></span>${escapeHtml(group.name)}${group.count > 1 ? ` ×${group.count}` : ""} · 当前 ${formatConcentration(current, group.unit)} · t1/2 ${group.halfLife.toFixed(1)}h`;
    legend.appendChild(item);
  });
}

function scheduleDataBrowser() {
  clearTimeout(scheduleDataBrowser.timer);
  scheduleDataBrowser.timer = setTimeout(renderDataBrowser, 180);
}

async function renderDataBrowser() {
  const list = $("dataList");
  const count = $("dataCount");
  if (!list || !count) return;
  const query = ($("dataSearch")?.value || "").trim();
  const token = ++state.dataRequestToken;
  list.className = "risk-list empty";
  list.textContent = query ? "\u68c0\u7d22\u4e2d..." : "\u52a0\u8f7d\u9ad8\u98ce\u9669\u6837\u4f8b...";
  const response = await fetch(`/api/interactions?q=${encodeURIComponent(query)}&limit=60`);
  const payload = await response.json();
  if (token !== state.dataRequestToken) return;
  count.textContent = `${payload.total ?? 0} \u6761\u5339\u914d`;
  const items = payload.items || [];
  if (!items.length) {
    const substanceMatches = query ? searchLocalSubstances(query, 30) : [];
    if (!substanceMatches.length && query && remoteEnabled()) {
      list.textContent = "\u672c\u5730\u65e0\u547d\u4e2d\uff0c\u6b63\u5728\u67e5\u8be2\u8fdc\u7a0b\u9759\u6001 API...";
      try {
        const remoteMatches = await searchRemoteSubstances(query, 30);
        if (token !== state.dataRequestToken) return;
        if (remoteMatches.length) {
          count.textContent = `\u8fdc\u7a0b ${remoteMatches.length} \u4e2a\u7269\u8d28\u5339\u914d \u00b7 \u672c\u5730 0 \u6761`;
          list.className = "risk-list";
          list.innerHTML = "";
          remoteMatches.forEach((substance) => list.appendChild(remoteSubstanceCard(substance)));
          return;
        }
      } catch (error) {
        if (token !== state.dataRequestToken) return;
        list.className = "risk-list empty";
        list.textContent = `\u8fdc\u7a0b\u6e90\u67e5\u8be2\u5931\u8d25\uff1a${error.message || error}`;
        return;
      }
    }
    if (!substanceMatches.length) {
      list.className = "risk-list empty";
      list.textContent = remoteEnabled() ? "\u672c\u5730\u548c\u8fdc\u7a0b\u6e90\u90fd\u6ca1\u6709\u5339\u914d\u7ed3\u679c\u3002" : "\u6ca1\u6709\u5339\u914d\u7ed3\u679c\u3002\u53ef\u5728\u8bbe\u7f6e\u9875\u542f\u7528\u8fdc\u7a0b\u9759\u6001 API \u56de\u9000\u3002";
      return;
    }
    count.textContent = `${substanceMatches.length} \u4e2a\u836f\u7269\u5339\u914d \u00b7 \u6682\u65e0\u76f8\u4e92\u4f5c\u7528\u8bb0\u5f55`;
    list.className = "risk-list";
    list.innerHTML = "";
    substanceMatches.forEach((substance) => list.appendChild(substanceCard(substance)));
    return;
  }
  list.className = "risk-list";
  list.innerHTML = "";
  items.forEach((interaction) => list.appendChild(interactionCard(interaction)));
}

function searchLocalSubstances(query, limit) {
  const normalized = query.trim().toLowerCase();
  const matches = [];
  for (const item of state.substances) {
    const haystack = `${item.id} ${item.name_en || ""} ${item.name_zh || ""} ${item.identifiers?.aliases || ""}`.toLowerCase();
    if (haystack.includes(normalized)) {
      matches.push(item);
      if (matches.length >= limit) break;
    }
  }
  return matches;
}

function substanceCard(substance) {
  const card = document.createElement("article");
  card.className = "risk-card";
  const aliases = substance.identifiers?.aliases ? `别名：${substance.identifiers.aliases}` : "";
  const remoteBadge = substance.remote_source ? `<span class="remote-badge">\u8fdc\u7a0b\u6e90</span>` : "";
  const category = categoryLabel(substance.category);
  const pk = `半衰期 ${substance.base_half_life ? `${Number(substance.base_half_life).toFixed(2)}h` : "未知"} · 起效 ${substance.base_onset || "未知"}min · 持续 ${substance.base_duration || "未知"}min`;
  card.innerHTML = `
    <header>
      <div class="card-title">${escapeHtml(substanceLabel(substance))}${remoteBadge}</div>
      <span class="badge Unknown">\u7269\u8d28</span>
    </header>
    <div class="card-meta">${escapeHtml(category)} \u00b7 ${escapeHtml(pk)}</div>
    <div class="card-note">${escapeHtml(substanceEffectSummary(substance))}</div>
    ${substance.cyp_tags?.length ? `<div class="card-note">代谢标签：${escapeHtml(substance.cyp_tags.join(", "))}</div>` : ""}
    ${aliases ? `<div class="card-note">${escapeHtml(aliases)}</div>` : ""}
    <div class="card-note">当前库中没有该物质的 DDInter 两两冲突记录；这不代表安全。</div>
  `;
  return card;
}

function riskSubjectText(risk) {
  if (["dose", "model", "signal"].includes(risk.risk_kind)) return risk.substance_name || substanceName(risk.substance_id);
  return `${risk.substance_a_name || substanceName(risk.substance_a_id)} \u00d7 ${risk.substance_b_name || substanceName(risk.substance_b_id)}`;
}

function consumerRiskAction(risk) {
  if (risk.risk_kind === "signal") return "\u8fd9\u662f\u516c\u5f00\u836f\u7269\u8b66\u6212\u5e93\u91cc\u7684\u5019\u9009\u4fe1\u53f7\uff0c\u53ea\u7528\u4e8e\u63d0\u9192\u4f60\u89c2\u5bdf\u5e76\u8bb0\u5f55\u75c7\u72b6\uff1b\u4e0d\u4ee3\u8868\u8be5\u836f\u4e00\u5b9a\u5bfc\u81f4\u8be5\u53cd\u5e94\uff0c\u4e5f\u4e0d\u4ee3\u8868\u8054\u7528\u51b2\u7a81\u3002";
  const score = riskSortValue(risk.risk_level);
  if (score >= 5) return "\u6682\u505c\u53e0\u52a0\u4f7f\u7528\uff0c\u4f18\u5148\u8054\u7cfb\u533b\u751f/\u836f\u5e08\uff1b\u51fa\u73b0\u660f\u7761\u3001\u547c\u5438\u5f02\u5e38\u3001\u80f8\u75db\u6216\u610f\u8bc6\u6539\u53d8\u65f6\u76f4\u63a5\u6025\u6551\u3002";
  if (score >= 4) return "\u4e0d\u8981\u7ee7\u7eed\u8ffd\u52a0\u5242\u91cf\uff0c\u5148\u62c9\u5f00\u65f6\u95f4\u5e76\u89c2\u5bdf\u72b6\u6001\uff1b\u5982\u6709\u4e0d\u9002\u5c31\u54a8\u8be2\u4e13\u4e1a\u4eba\u5458\u3002";
  if (score >= 3) return "\u53ef\u80fd\u4f1a\u589e\u5f3a\u6216\u5ef6\u957f\u4f5c\u7528\uff0c\u5efa\u8bae\u4fdd\u5b88\u8ffd\u52a0\u3001\u907f\u514d\u540c\u65f6\u7528\u9152\u6216\u5176\u4ed6\u6291\u5236/\u5174\u594b\u7269\u3002";
  return "\u8bb0\u5f55\u5e76\u89c2\u5bdf\u5373\u53ef\uff1b\u82e5\u75c7\u72b6\u53d8\u5316\u660e\u663e\uff0c\u518d\u5207\u6362 ToB \u67e5\u770b\u6765\u6e90\u7ec6\u8282\u3002";
}

function consumerRiskCard(risk) {
  const card = document.createElement("article");
  card.className = "risk-card consumer-risk-card";
  const subject = riskSubjectText(risk);
  const note = risk.risk_kind === "model"
    ? (risk.note || "PopPK \u6a21\u578b\u8b66\u544a")
    : risk.risk_kind === "signal"
      ? (risk.note || "\u836f\u7269\u8b66\u6212\u5019\u9009\u4fe1\u53f7")
      : localizeInteractionNote(risk.note || "");
  const type = risk.risk_kind === "dose"
    ? "\u5242\u91cf/\u8fc7\u91cf"
    : risk.risk_kind === "model"
      ? "\u4ee3\u8c22\u6a21\u578b"
      : risk.risk_kind === "signal"
        ? "\u4e0d\u826f\u4e8b\u4ef6\u5019\u9009\u4fe1\u53f7"
        : "\u8054\u7528\u51b2\u7a81";
  card.innerHTML = `
    <header>
      <div class="card-title">${escapeHtml(subject)}</div>
      <span class="badge ${escapeHtml(risk.risk_level)}">${escapeHtml(riskLevelLabel(risk.risk_level))}</span>
    </header>
    <div class="card-meta">${escapeHtml(type)}</div>
    <div class="consumer-action"><strong>\u5efa\u8bae</strong>${escapeHtml(consumerRiskAction(risk))}</div>
    ${note ? `<div class="consumer-reason"><strong>\u539f\u56e0</strong>${escapeHtml(note)}</div>` : ""}
  `;
  return card;
}

function remoteSubstanceCard(substance) {
  const card = substanceCard({ ...substance, remote_source: substance.remote_source || "remote_static_api" });
  const note = document.createElement("div");
  note.className = "remote-add-row";
  note.innerHTML = `<button class="ghost" type="button" data-add-remote-substance="${escapeHtml(substance.id)}">\u52a0\u5165\u672c\u5730\u5019\u9009\u5e76\u53ef\u8bb0\u5f55</button>`;
  card.appendChild(note);
  return card;
}

function riskCard(risk) {
  if (!state.advancedMode) return consumerRiskCard(risk);
  if (risk.risk_kind === "dose") return doseRiskCard(risk);
  if (risk.risk_kind === "model") return modelRiskCard(risk);
  if (risk.risk_kind === "signal") return signalRiskCard(risk);
  return interactionCard(risk);
}

function modelRiskCard(risk) {
  const card = document.createElement("article");
  card.className = "risk-card";
  const sourceTier = sourceTierLabel(risk.source_tier || "Literature");
  const confidence = confidenceLabel(risk.confidence || "Low");
  const type = interactionTypeLabel(risk.interaction_type || "pharmacokinetics");
  card.innerHTML = `
    <header>
      <div class="card-title">${escapeHtml(risk.substance_name || risk.substance_id)} \u00b7 PopPK \u6a21\u578b\u9884\u8b66</div>
      <span class="badge ${escapeHtml(risk.risk_level)}">${escapeHtml(riskLevelLabel(risk.risk_level))}</span>
    </header>
    <div class="card-meta">\u6765\u6e90\u5c42\u7ea7\uff1a${escapeHtml(sourceTier)} \u00b7 \u53ef\u4fe1\u5ea6\uff1a${escapeHtml(confidence)} \u00b7 \u7c7b\u578b\uff1a${escapeHtml(type)}</div>
    <div class="card-note">${escapeHtml(risk.note || "")}</div>
    <div class="card-note">\u6765\u6e90\uff1a${escapeHtml(risk.source_name || "PopPK \u8ba1\u7b97\u5f15\u64ce")}</div>
  `;
  return card;
}

function doseRiskCard(risk) {
  const card = document.createElement("article");
  card.className = "risk-card";
  const sourceTier = sourceTierLabel(risk.source_tier || "DoseRule");
  const confidence = confidenceLabel(risk.confidence || "Unknown");
  const type = interactionTypeLabel(risk.interaction_type || "dose_safety");
  card.innerHTML = `
    <header>
      <div class="card-title">${escapeHtml(risk.substance_name || risk.substance_id)} \u00b7 \u8fc7\u91cf\u98ce\u9669</div>
      <span class="badge ${escapeHtml(risk.risk_level)}">${escapeHtml(riskLevelLabel(risk.risk_level))}</span>
    </header>
    <div class="card-meta">\u6765\u6e90\u5c42\u7ea7\uff1a${escapeHtml(sourceTier)} \u00b7 \u53ef\u4fe1\u5ea6\uff1a${escapeHtml(confidence)} \u00b7 \u7c7b\u578b\uff1a${escapeHtml(type)}</div>
    <div class="card-note">${escapeHtml(risk.note || "")}</div>
    <div class="card-note">\u6765\u6e90\uff1a${escapeHtml(risk.source_name || "\u672c\u5730\u5242\u91cf\u89c4\u5219")}</div>
  `;
  return card;
}
function signalRiskCard(risk) {
  const card = document.createElement("article");
  card.className = "risk-card";
  const sourceTier = sourceTierLabel(risk.source_tier || "Signal");
  const confidence = confidenceLabel(risk.confidence || "Low");
  const type = interactionTypeLabel(risk.interaction_type || "adverse_event_signal");
  const reactions = Array.isArray(risk.reactions) && risk.reactions.length
    ? risk.reactions.map((item) => `${item.label || item.reaction} ${Number(item.count || 0).toLocaleString()} \u4f8b`).join("\uff1b")
    : "\u6682\u65e0\u53ef\u5c55\u793a\u660e\u7ec6";
  card.innerHTML = `
    <header>
      <div class="card-title">${escapeHtml(risk.substance_name || substanceName(risk.substance_id))} \u00b7 \u836f\u7269\u8b66\u6212\u5019\u9009\u4fe1\u53f7</div>
      <span class="badge ${escapeHtml(risk.risk_level)}">${escapeHtml(riskLevelLabel(risk.risk_level))}</span>
    </header>
    <div class="card-meta">\u6765\u6e90\u5c42\u7ea7\uff1a${escapeHtml(sourceTier)} \u00b7 \u53ef\u4fe1\u5ea6\uff1a${escapeHtml(confidence)} \u00b7 \u7c7b\u578b\uff1a${escapeHtml(type)}</div>
    <div class="card-note">\u5171\u62a5\u544a\u4e8b\u4ef6\uff1a${escapeHtml(reactions)}</div>
    <div class="card-note">${escapeHtml(risk.note || "FAERS \u4fe1\u53f7\u4e0d\u4ee3\u8868\u56e0\u679c\u5173\u7cfb\uff0c\u4ec5\u7528\u4e8e\u89c2\u5bdf\u63d0\u9192\u3002")}</div>
    <div class="card-note">\u6765\u6e90\uff1a${escapeHtml(risk.source_name || "openFDA FAERS adverse event")}</div>
  `;
  return card;
}

function interactionCard(interaction) {
  const card = document.createElement("article");
  card.className = "risk-card";
  const aName = interaction.substance_a_name || substanceName(interaction.substance_a_id);
  const bName = interaction.substance_b_name || substanceName(interaction.substance_b_id);
  const aSubstance = state.substanceById.get(interaction.substance_a_id) || { id: interaction.substance_a_id, name_en: interaction.substance_a_name_en };
  const bSubstance = state.substanceById.get(interaction.substance_b_id) || { id: interaction.substance_b_id, name_en: interaction.substance_b_name_en };
  const effectLine = `${aName}：${compactSubstanceEffect(aSubstance)} · ${bName}：${compactSubstanceEffect(bSubstance)}`;
  const sourceTier = sourceTierLabel(interaction.source_tier || "Unknown");
  const confidence = confidenceLabel(interaction.confidence || "Unknown");
  const type = interactionTypeLabel(interaction.interaction_type || "");
  const note = localizeInteractionNote(interaction.note);
  card.innerHTML = `
    <header>
      <div class="card-title">${escapeHtml(aName)} \u00d7 ${escapeHtml(bName)}</div>
      <span class="badge ${escapeHtml(interaction.risk_level)}">${escapeHtml(riskLevelLabel(interaction.risk_level))}</span>
    </header>
    <div class="card-meta">\u6765\u6e90\u5c42\u7ea7\uff1a${escapeHtml(sourceTier)} \u00b7 \u53ef\u4fe1\u5ea6\uff1a${escapeHtml(confidence)} \u00b7 \u7c7b\u578b\uff1a${escapeHtml(type)}</div>
    <div class="card-note">\u4f5c\u7528：${escapeHtml(effectLine)}</div>
    ${note ? `<div class="card-note">${escapeHtml(note)}</div>` : ""}
  `;
  return card;
}

async function renderSources() {
  const list = $("sourceStatus");
  const count = $("sourceCount");
  if (!list || !count) return;
  const token = ++state.sourceRequestToken;
  const response = await fetch("/api/sources");
  const payload = await response.json();
  if (token !== state.sourceRequestToken) return;
  state.sources = payload.items || [];
  updateKpis();
  count.textContent = `${state.sources.length} 个源 · 候选事实 ${payload.optionalFactsCount || 0}`;
  list.className = "source-status";
  list.innerHTML = "";
  state.sources.forEach((source) => list.appendChild(sourceCard(source)));
}

function sourceUpdateSummary(source) {
  const lastUpdate = source.last_update || null;
  if (!lastUpdate?.updated_at) {
    if (source.status?.includes("pending")) return "\u672a\u63a5\u5165";
    if (source.optional_facts_count) return `\u5df2\u6709\u5019\u9009\u4e8b\u5b9e ${source.optional_facts_count} \u6761\uff0c\u672a\u8bb0\u5f55\u540c\u6b65\u65f6\u95f4`;
    return "\u5c1a\u672a\u5355\u72ec\u540c\u6b65";
  }
  let last = `\u4e0a\u6b21\u66f4\u65b0\uff1a${new Date(lastUpdate.updated_at).toLocaleString()}`;
  if (lastUpdate.mode === "public_sync") {
    const facts = lastUpdate.facts ?? 0;
    const attempted = lastUpdate.attempted ?? 0;
    const errors = lastUpdate.errors ?? 0;
    last += ` \u00b7 \u672c\u6279\u547d\u4e2d ${facts} / \u8bf7\u6c42 ${attempted}${errors ? `\uff0c\u8df3\u8fc7 ${errors}` : ""}`;
  } else if (lastUpdate.mode === "bulk_download") {
    last += ` \u00b7 \u5168\u91cf\u6587\u4ef6 ${lastUpdate.files || 0} \u4e2a${lastUpdate.total_size_mb ? ` \u00b7 \u7ea6 ${(Number(lastUpdate.total_size_mb) / 1024).toFixed(1)}GB` : ""}`;
  } else if (lastUpdate.mode === "api_full") {
    last += ` \u00b7 \u5168\u91cf\u5019\u9009\u4e8b\u5b9e ${lastUpdate.facts || 0} \u6761`;
  } else if (lastUpdate.mode === "local_source_ready" || lastUpdate.mode === "included_in_full_rebuild") {
    last += ` \u00b7 \u5df2\u7eb3\u5165\u672c\u5730\u5e93`;
  } else if (lastUpdate.facts !== undefined) {
    last += ` \u00b7 \u83b7\u53d6 ${lastUpdate.facts} \u6761`;
  }
  return last;
}

function sourceCard(source) {
  const card = document.createElement("article");
  card.className = `source-card ${source.can_update || source.can_bulk_update ? "" : "disabled"}`;
  const last = sourceUpdateSummary(source);
  const directLabel = source.is_direct_public ? "公开 API" : source.status === "license_required" ? "需授权" : source.status?.includes("pending") ? "待接入" : "本地已纳入";
  const updateLabel = source.key === "psychonautwiki" ? "批量同步候选" : "按当前物质补充";
  const onlineLabel = source.status === "license_required" ? "商业授权后接入线上库" : "线上库统一融合";
  const rebuildLine = source.last_update?.mode === "included_in_full_rebuild" ? "已纳入最近一次全量重建。" : "";
  const factLine = source.is_direct_public ? `候选事实：${source.optional_facts_count || 0} 条` : "";
  const scopeLine = source.is_direct_public && source.key !== "psychonautwiki"
    ? "按当前物质补充只做本地临时补盲；线上全量库由 GitHub Actions 统一融合构建，本地应用不会自动下载大包。"
    : "";
  card.innerHTML = `
    <header>
      <div class="card-title">${escapeHtml(source.name)}</div>
      <span class="badge Unknown">${escapeHtml(source.tier)}</span>
    </header>
    <div class="card-meta">${escapeHtml(source.status)} · ${escapeHtml(directLabel)} · ${escapeHtml(last)}</div>
    <div class="card-note">${escapeHtml(source.note || "")}</div>
    ${factLine ? `<div class="card-note">${escapeHtml(factLine)}</div>` : ""}
    ${rebuildLine ? `<div class="card-note">${escapeHtml(rebuildLine)}</div>` : ""}
    ${scopeLine ? `<div class="card-note">${escapeHtml(scopeLine)}</div>` : ""}
    <div class="card-note">${escapeHtml(source.url || "")}</div>
    <div class="source-actions">
      ${source.is_direct_public ? `<button class="ghost" type="button" data-update-source="${escapeHtml(source.key)}">${escapeHtml(updateLabel)}</button>` : ""}
      ${source.can_bulk_update ? `<button class="ghost" type="button" disabled>${escapeHtml(onlineLabel)}</button>` : ""}
      ${source.status === "license_required" ? `<button class="ghost" type="button" disabled>商业授权后接入</button>` : ""}
    </div>
  `;
  return card;
}
async function updateSource(key) {
  const source = state.sources.find((item) => item.key === key);
  const term = selectedSourceTerm();
  if (source?.is_direct_public && source.key !== "psychonautwiki" && !term) {
    setSourceMessage("\u6ca1\u6709\u53ef\u7528\u5173\u952e\u8bcd\uff1a\u8bf7\u5148\u9009\u62e9\u4e00\u4e2a\u7269\u8d28\uff0c\u6216\u5728\u4e0a\u65b9\u8f93\u5165\u6307\u5b9a\u5173\u952e\u8bcd\u3002", true);
    return;
  }
  setSourceMessage(`\u6b63\u5728\u66f4\u65b0 ${source?.name || key}${term ? ` \u00b7 ${term}` : ""}...`, false);
  const params = new URLSearchParams({ key, limit: key === "psychonautwiki" ? "50" : "5" });
  if (term) params.set("term", term);
  const response = await fetch(`/api/source-update?${params.toString()}`);
  const payload = await response.json();
  setSourceMessage(payload.message || (payload.ok ? "\u66f4\u65b0\u5b8c\u6210\u3002" : "\u66f4\u65b0\u5931\u8d25\u3002"), !payload.ok);
  await renderSources();
}

async function bulkSyncSource(key) {
  const source = state.sources.find((item) => item.key === key);
  setSourceMessage(`本地桌面应用不直接下载 ${source?.name || key} 的全量大包；全量原始库只用于离线结构化分析，请用 ETL 命令 mirror-raw-sources 拉到 D 盘镜像目录。`, true);
}
function setTaskButtonsDisabled(disabled) {
  ["rebuildDataset", "syncPublicSources", "bulkSyncAll", "labelBulkManifest"].forEach((id) => {
    const element = $(id);
    if (element) element.disabled = disabled;
  });
  document.querySelectorAll("[data-update-source], [data-bulk-source]").forEach((button) => {
    button.disabled = disabled;
  });
}

async function rebuildDatasetFromSettings() {
  setTaskButtonsDisabled(true);
  setRebuildProgress(0, "\u542f\u52a8\u5168\u91cf\u91cd\u5efa...");
  const response = await fetch("/api/rebuild");
  const payload = await response.json();
  if (!payload.ok) {
    setTaskButtonsDisabled(false);
    setRebuildProgress(100, payload.message || "\u91cd\u5efa\u542f\u52a8\u5931\u8d25\u3002", true);
    setSourceMessage(payload.message || "\u91cd\u5efa\u5931\u8d25\u3002", true);
    return;
  }
  const jobId = payload.jobId;
  if (!jobId) {
    setTaskButtonsDisabled(false);
    setRebuildProgress(100, "\u6ca1\u6709\u62ff\u5230\u91cd\u5efa\u4efb\u52a1 ID\u3002", true);
    return;
  }
  await pollRebuildJob(jobId);
}


async function showLabelBulkManifest() {
  setSourceMessage("正在读取 openFDA / DailyMed 官方全量标签包清单...", false);
  const response = await fetch("/api/label-bulk-manifest");
  const payload = await response.json();
  if (!payload.ok) {
    setSourceMessage(payload.message || "读取全量标签包清单失败。", true);
    return;
  }
  const sourceNames = {
    openfda_label: "openFDA Drug Label",
    dailymed: "DailyMed SPL",
  };
  const lines = (payload.items || []).map((item) => {
    if (item.error) return `${item.source}: ${item.error} ${item.message || ""}`;
    const parts = item.parts || [];
    const sizeMb = item.total_size_mb || parts.reduce((sum, part) => sum + Number(part.size_mb || 0), 0);
    const records = item.total_records || parts.reduce((sum, part) => sum + Number(part.records || 0), 0);
    return `${sourceNames[item.source] || item.source}：${parts.length} 个 zip 分包，${Number(records || 0).toLocaleString("zh-CN")} 条标签/文件，约 ${(sizeMb / 1024).toFixed(1)} GB`;
  });
  setSourceMessage(`这是官方全量下载包清单，当前页面不会下载大包：${lines.join("；")}。D 盘原始库镜像只用于离线 ETL 和结构化分析，不作为本地应用运行时数据库。`, false);
}
async function showRemoteFullLibrary() {
  saveRemoteConfigFromControls();
  if (!state.remoteConfig.baseUrl) {
    setSourceMessage("\u8bf7\u5148\u5728\u8fdc\u7a0b\u9759\u6001 API \u5730\u5740\u4e2d\u586b\u5199 本机镜像 /remote-api 或 GitHub Pages /api\u3002", true);
    return;
  }
  setSourceMessage("\u6b63\u5728\u8bfb\u53d6\u7ebf\u4e0a\u5168\u91cf\u878d\u5408\u5e93 manifest...", false);
  const manifest = await fetchRemoteJson("manifest.json", { cache: "no-cache" });
  state.remoteManifest = manifest;
  const counts = manifest.counts || {};
  const online = manifest.online_library || {};
  const sourceLibrary = online.source_library || manifest.source_library || {};
  const fullPackage = online.full_package || manifest.full_package || {};
  let packageDetail = null;
  if (fullPackage.manifest) {
    try {
      packageDetail = await fetchRemoteJson(fullPackage.manifest, { cache: "no-cache" });
    } catch {
      packageDetail = null;
    }
  }
  const zipBytes = packageDetail?.files?.zip_bytes || fullPackage.zip_bytes || 0;
  const sourceCount = sourceLibrary.sources_count || packageDetail?.source_library?.sources_count || 0;
  const factCount = sourceLibrary.facts_count || packageDetail?.source_library?.facts_count || 0;
  const message = `\u7ebf\u4e0a\u5168\u91cf\u5e93\u5df2\u5c31\u7eea\uff1a${formatNumber(counts.substances || 0, 0)} \u4e2a\u7269\u8d28\uff0c${formatNumber(counts.interactions || 0, 0)} \u6761\u76f8\u4e92\u4f5c\u7528\uff0c${formatNumber(counts.dose_rules || 0, 0)} \u6761\u5242\u91cf\u89c4\u5219\uff0c${formatNumber(counts.dose_candidates || 0, 0)} \u6761\u5242\u91cf\u5019\u9009\uff0c${formatNumber(counts.overdose_warnings || 0, 0)} \u6761\u8fc7\u91cf\u8b66\u544a\uff1b\u6e90\u5c42 ${formatNumber(sourceCount, 0)} \u4e2a\uff0c\u8bc1\u636e\u4e8b\u5b9e ${formatNumber(factCount, 0)} \u6761\uff1b\u5168\u91cf\u5305 ${formatBytes(zipBytes)}\u3002dose_candidate / overdose_warning \u662f\u8bc1\u636e\u5019\u9009\uff0c\u4e0d\u7b49\u4e8e\u53ef\u76f4\u63a5\u62a5\u8b66\u7684 dose_rule\u3002\u672c\u5730\u4ecd\u4fdd\u7559\u539f\u672c\u8f7b\u91cf\u65b9\u6848\uff0c\u4e0d\u4f1a\u81ea\u52a8\u4e0b\u8f7d\u5168\u91cf\u5305\u3002`;
  setSourceMessage(message, false);
  setRemoteApiStatus(message, "ok");
}

async function syncPublicSourcesFromSettings() {
  setTaskButtonsDisabled(true);
  setRebuildProgress(0, "\u542f\u52a8\u8054\u7f51\u540c\u6b65\u516c\u5f00\u6e90...");
  const response = await fetch("/api/public-sync?maxTerms=80");
  const payload = await response.json();
  if (!payload.ok || !payload.jobId) {
    setTaskButtonsDisabled(false);
    setRebuildProgress(100, payload.message || "\u516c\u5f00\u6e90\u540c\u6b65\u542f\u52a8\u5931\u8d25\u3002", true);
    return;
  }
  await pollRebuildJob(payload.jobId);
}

async function pollRebuildJob(jobId) {
  let finalMessage = "";
  for (;;) {
    const payload = await fetch(`/api/rebuild-status?job=${encodeURIComponent(jobId)}`).then((res) => res.json());
    if (!payload.ok) {
      setTaskButtonsDisabled(false);
      setRebuildProgress(100, payload.message || "\u8bfb\u53d6\u4efb\u52a1\u8fdb\u5ea6\u5931\u8d25\u3002", true);
      setSourceMessage(payload.message || "\u8bfb\u53d6\u4efb\u52a1\u8fdb\u5ea6\u5931\u8d25\u3002", true);
      return;
    }
    setRebuildProgress(payload.progress || 0, payload.message || "\u4efb\u52a1\u8fdb\u884c\u4e2d...");
    if (payload.status === "error") {
      setTaskButtonsDisabled(false);
      setRebuildProgress(100, payload.message || "\u4efb\u52a1\u5931\u8d25\u3002", true);
      setSourceMessage(payload.message || "\u4efb\u52a1\u5931\u8d25\u3002", true);
      return;
    }
    if (payload.status === "done") {
      finalMessage = payload.message || "\u4efb\u52a1\u5b8c\u6210\u3002";
      break;
    }
    await sleep(700);
  }
  const seed = await fetch("/api/seed").then((res) => res.json());
  state.manifest = seed.manifest;
  state.substances = seed.substances || [];
  state.substanceById = new Map(state.substances.map((item) => [item.id, item]));
  state.doseRules = seed.doseRules || [];
  mergeRemoteCachedSubstances();
  setTaskButtonsDisabled(false);
  setRebuildProgress(100, finalMessage || "\u4efb\u52a1\u5b8c\u6210\uff0c\u5df2\u52a0\u8f7d\u6700\u65b0\u672c\u5730\u5e93\u3002", false);
  refresh();
  await renderSources();
}

function setRebuildProgress(progress, message, isError = false) {
  const panel = $("rebuildProgress");
  const bar = $("rebuildProgressBar");
  const text = $("rebuildProgressText");
  if (!panel || !bar || !text) return;
  panel.classList.remove("hidden");
  bar.style.width = `${Math.max(0, Math.min(Number(progress || 0), 100))}%`;
  bar.style.background = isError ? "var(--red)" : "var(--green)";
  text.textContent = `${Math.round(progress || 0)}% · ${message}`;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function setSourceMessage(message, isError = false) {
  const list = $("sourceStatus");
  if (!list) return;
  const prefix = isError ? "错误：" : "";
  list.className = "source-status empty";
  list.textContent = `${prefix}${message}`;
}

function refresh() {
  renderMeta();
  renderSubstanceOptions();
  renderJournal();
  refreshRisks().catch(console.error);
  if (state.advancedMode) renderDataBrowser().catch(console.error);
  drawCurve();
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#039;",
    '"': "&quot;",
  }[char]));
}

async function boot() {
  const response = await fetch("/api/seed");
  const payload = await response.json();
  state.manifest = payload.manifest;
  state.substances = payload.substances || [];
  state.substanceById = new Map(state.substances.map((item) => [item.id, item]));
  state.doseRules = payload.doseRules || [];
  if ($("bulkSyncAll")) $("bulkSyncAll").textContent = "查看线上全量库";
  loadRemoteConfig();
  loadProfile();
  loadJournal();
  loadCurveZoom();
  loadUiMode();
  loadThemeMode();
  resetIntakeTime();
  refresh();
  if (state.advancedMode) renderSources().catch(console.error);
  requestAnimationFrame(drawCurve);
}


function togglePmiHelp(open = null) {
  const dialog = $("pmiHelpDialog");
  const button = $("pmiHelpButton");
  if (!dialog) return;
  const shouldOpen = open === null ? dialog.classList.contains("hidden") : Boolean(open);
  dialog.classList.toggle("hidden", !shouldOpen);
  button?.setAttribute("aria-expanded", shouldOpen ? "true" : "false");
}
$("entryForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const selected = $("substanceSelect").value;
  if (!selected) return;
  syncEthanolCalculator(true);
  const ethanolDose = isEthanolSubstance(selected) ? calculateEthanolDose() : null;
  const intakeTimestamp = fromDateTimeLocal($("intakeTimeInput")?.value);
  state.journal.push({
    id: crypto.randomUUID ? crypto.randomUUID() : String(Date.now()),
    timestamp: intakeTimestamp,
    substanceId: selected,
    dosage: ethanolDose ? Number(ethanolDose.grams.toFixed(1)) : Number($("dosageInput").value),
    unit: $("unitSelect").value,
    route: $("routeSelect").value,
    stomachState: $("stomachSelect").value,
    ethanol: ethanolDose ? { ...ethanolDose, grams: Number(ethanolDose.grams.toFixed(1)) } : null,
    note: $("noteInput").value.trim(),
  });
  $("noteInput").value = "";
  resetIntakeTime();
  saveJournal();
  renderMeta();
  renderJournal();
  refreshRisks().catch(console.error);
  drawCurve();
});

$("clearJournal").addEventListener("click", () => {
  state.journal = [];
  state.activeRisks = [];
  saveJournal();
  renderJournal();
  renderRisks();
  drawCurve();
});

$("journalList").addEventListener("click", (event) => {
  const button = event.target.closest("[data-delete-entry]");
  if (!button) return;
  const id = button.getAttribute("data-delete-entry");
  state.journal = state.journal.filter((entry) => entry.id !== id);
  saveJournal();
  renderJournal();
  refreshRisks().catch(console.error);
  drawCurve();
});

["weightInput", "heightInput", "ageInput", "bodyFatInput", "sleepDebtInput", "coreTempInput"].forEach((id) => {
  $(id)?.addEventListener("input", () => {
    saveProfile();
    renderMeta();
    renderJournal();
    refreshRisks().catch(console.error);
    drawCurve();
  });
});


$("doseSlider")?.addEventListener("input", () => {
  $("dosageInput").value = $("doseSlider").value;
});
$("dosageInput")?.addEventListener("input", () => {
  syncDoseSlider($("dosageInput").value);
});
$("substanceSelect")?.addEventListener("change", () => {
  syncEthanolCalculator(true);
  renderSelectedSubstanceInfo();
});
$("drinkVolumeInput")?.addEventListener("input", () => syncEthanolCalculator(true));
$("drinkAbvInput")?.addEventListener("input", () => syncEthanolCalculator(true));
$("substanceFilter")?.addEventListener("input", renderSubstanceOptions);
$("dataSearch")?.addEventListener("input", scheduleDataBrowser);
$("dataList")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-add-remote-substance]");
  if (!button) return;
  const id = button.getAttribute("data-add-remote-substance");
  button.disabled = true;
  button.textContent = "\u6b63\u5728\u52a0\u5165...";
  addRemoteSubstanceById(id)
    .then((detail) => {
      $("substanceFilter").value = detail.name_zh || detail.name_en || detail.id;
      renderSubstanceOptions();
      $("substanceSelect").value = detail.id;
      renderSelectedSubstanceInfo();
      button.textContent = "\u5df2\u52a0\u5165\u672c\u5730\u5019\u9009";
    })
    .catch((error) => {
      button.disabled = false;
      button.textContent = "\u52a0\u5165\u5931\u8d25\uff0c\u91cd\u8bd5";
      setRemoteApiStatus(error.message || String(error), "error");
    });
});
$("remoteFallbackEnabled")?.addEventListener("change", () => {
  saveRemoteConfigFromControls();
  renderSubstanceOptions();
  renderDataBrowser().catch(console.error);
});
$("remoteApiBase")?.addEventListener("change", saveRemoteConfigFromControls);
$("remoteApiSave")?.addEventListener("click", () => {
  saveRemoteConfigFromControls();
  setRemoteApiStatus("\u8fdc\u7a0b\u6e90\u914d\u7f6e\u5df2\u4fdd\u5b58\u3002", "ok");
});
$("remoteApiTest")?.addEventListener("click", () => {
  testRemoteApiConnection().catch((error) => setRemoteApiStatus(error.message || String(error), "error"));
});
$("sourceStatus")?.addEventListener("click", (event) => {
  const updateButton = event.target.closest("[data-update-source]");
  if (updateButton) {
    updateSource(updateButton.getAttribute("data-update-source")).catch((error) => setSourceMessage(error.message, true));
    return;
  }
  const bulkButton = event.target.closest("[data-bulk-source]");
  if (bulkButton) {
    bulkSyncSource(bulkButton.getAttribute("data-bulk-source")).catch((error) => {
      setTaskButtonsDisabled(false);
      setSourceMessage(error.message, true);
    });
  }
});
$("pmiHelpButton")?.addEventListener("click", () => togglePmiHelp());
$("pmiHelpClose")?.addEventListener("click", () => togglePmiHelp(false));
$("pmiHelpDialog")?.addEventListener("click", (event) => {
  if (event.target === $("pmiHelpDialog")) togglePmiHelp(false);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") togglePmiHelp(false);
});
$("advancedModeToggle")?.addEventListener("change", (event) => setAdvancedMode(event.target.checked));
$("themeModeSelect")?.addEventListener("change", (event) => setThemeMode(event.target.value));
$("rebuildDataset")?.addEventListener("click", () => {
  rebuildDatasetFromSettings().catch((error) => setSourceMessage(error.message, true));
});
$("syncPublicSources")?.addEventListener("click", () => {
  syncPublicSourcesFromSettings().catch((error) => setSourceMessage(error.message, true));
});
$("labelBulkManifest")?.addEventListener("click", () => {
  showLabelBulkManifest().catch((error) => setSourceMessage(error.message, true));
});
$("bulkSyncAll")?.addEventListener("click", () => {
  showRemoteFullLibrary().catch((error) => {
    setTaskButtonsDisabled(false);
    setSourceMessage(error.message, true);
  });
});
$("legend")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-curve-filter], [data-curve-substance]");
  if (!button) return;
  const activeIds = [...new Set(activeEntries().map((entry) => entry.substanceId).filter(Boolean))];
  if (button.dataset.curveFilter === "all") {
    state.curveHiddenSubstances.clear();
    requestCurveDraw();
    return;
  }
  const id = button.dataset.curveSubstance;
  if (!id || !activeIds.includes(id)) return;
  if (event.ctrlKey || event.metaKey || event.shiftKey) {
    if (state.curveHiddenSubstances.has(id)) state.curveHiddenSubstances.delete(id);
    else state.curveHiddenSubstances.add(id);
    if (activeIds.every((activeId) => state.curveHiddenSubstances.has(activeId))) {
      state.curveHiddenSubstances.clear();
    }
  } else {
    const alreadyIsolated = activeIds.length > 1
      && !state.curveHiddenSubstances.has(id)
      && activeIds.every((activeId) => activeId === id || state.curveHiddenSubstances.has(activeId));
    if (alreadyIsolated || activeIds.length <= 1) {
      state.curveHiddenSubstances.clear();
    } else {
      state.curveHiddenSubstances = new Set(activeIds.filter((activeId) => activeId !== id));
    }
  }
  requestCurveDraw();
});
$("curvePanLeft")?.addEventListener("click", () => panCurveByFraction(-0.25));
$("curveZoomOut")?.addEventListener("click", () => zoomCurve(1 / 1.25));
$("curveZoomIn")?.addEventListener("click", () => zoomCurve(1.25));
$("curvePanRight")?.addEventListener("click", () => panCurveByFraction(0.25));
$("curveZoomReset")?.addEventListener("click", resetCurveView);
$("curveZoomSlider")?.addEventListener("input", () => setCurveZoom($("curveZoomSlider").value));
const curveCanvasElement = $("curveCanvas");
if (curveCanvasElement) {
  curveCanvasElement.addEventListener("mousemove", (event) => {
    const rect = curveCanvasElement.getBoundingClientRect();
    const left = 56;
    const right = 12;
    const ratio = (event.clientX - rect.left - left) / Math.max(1, rect.width - left - right);
    state.curveHoverRatio = Math.max(0, Math.min(1, ratio));
    requestAnimationFrame(drawCurve);
  });
  curveCanvasElement.addEventListener("mouseleave", () => {
    state.curveHoverRatio = null;
    requestAnimationFrame(drawCurve);
  });
  curveCanvasElement.addEventListener("wheel", (event) => {
    event.preventDefault();
    if (event.shiftKey) {
      const viewport = curveViewport(activeEntries(), Date.now());
      panCurveByMinutes(viewport.horizonMinutes * (event.deltaY > 0 ? 0.08 : -0.08));
      return;
    }
    zoomCurve(event.deltaY < 0 ? 1.15 : 1 / 1.15);
  }, { passive: false });
  curveCanvasElement.addEventListener("pointerdown", (event) => {
    const viewport = curveViewport(activeEntries(), Date.now());
    const rect = curveCanvasElement.getBoundingClientRect();
    state.curveDrag = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startPan: state.curvePanMinutes,
      horizonMinutes: viewport.horizonMinutes,
      plotWidth: Math.max(1, rect.width - 64),
    };
    curveCanvasElement.classList.add("dragging");
    curveCanvasElement.setPointerCapture?.(event.pointerId);
    event.preventDefault();
  });
  curveCanvasElement.addEventListener("pointermove", (event) => {
    if (!state.curveDrag || state.curveDrag.pointerId !== event.pointerId) return;
    const dx = event.clientX - state.curveDrag.startX;
    const minutesDelta = -(dx / state.curveDrag.plotWidth) * state.curveDrag.horizonMinutes;
    setCurvePan(state.curveDrag.startPan + minutesDelta);
    event.preventDefault();
  });
  ["pointerup", "pointercancel", "lostpointercapture"].forEach((type) => {
    curveCanvasElement.addEventListener(type, () => {
      state.curveDrag = null;
      curveCanvasElement.classList.remove("dragging");
    });
  });
}
window.addEventListener("resize", () => requestAnimationFrame(drawCurve));
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) requestAnimationFrame(drawCurve);
});
setInterval(() => {
  refreshRisks().catch(console.error);
  drawCurve();
}, 30000);

boot().catch((error) => {
  console.error(error);
  $("datasetMeta").textContent = "\u52a0\u8f7d\u5931\u8d25\uff0c\u8bf7\u5148\u8fd0\u884c ETL import-ddinter \u751f\u6210 build \u6570\u636e\u3002";
});









