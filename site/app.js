const state = {
  manifest: null,
  searchManifest: null,
  sourceIndex: null,
  searchIndex: [],
  searchShardCache: new Map(),
  activeRows: [],
  renderToken: 0,
  searchDebounce: 0,
  activeId: "",
  query: "",
};

const $ = (id) => document.getElementById(id);

const riskRank = {
  Contraindicated: 6,
  Dangerous: 5,
  Unsafe: 5,
  Major: 4,
  Moderate: 3,
  Synergy: 2,
  Minor: 2,
  "Low Risk": 1,
  NoKnownClinicalSignificance: 1,
  Unknown: 0,
};

const riskLabels = {
  Contraindicated: "\u7edd\u5bf9\u7981\u5fcc",
  Dangerous: "\u9ad8\u5371",
  Unsafe: "\u4e0d\u5b89\u5168",
  Major: "\u4e25\u91cd",
  Moderate: "\u4e2d\u5ea6",
  Synergy: "\u534f\u540c/\u589e\u5f3a",
  Minor: "\u8f7b\u5fae",
  "Low Risk": "\u4f4e\u98ce\u9669",
  NoKnownClinicalSignificance: "\u65e0\u660e\u786e\u4e34\u5e8a\u610f\u4e49",
  Unknown: "\u672a\u77e5",
};

const ui = {
  unknown: "\u672a\u77e5",
  unknownSubstance: "\u672a\u547d\u540d\u836f\u7269",
  fetchFailed: "\u8bfb\u53d6\u5931\u8d25",
  category: "\u7c7b\u522b",
  solubility: "\u6eb6\u89e3\u6027",
  halfLife: "\u57fa\u51c6\u534a\u8870\u671f",
  onsetDuration: "\u8d77\u6548 / \u6301\u7eed",
  identity: "\u8eab\u4efd\u4e0e\u6765\u6e90",
  aliases: "\u522b\u540d\uff1a",
  cyp: "CYP / \u4ee3\u8c22\u6807\u7b7e\uff1a",
  summary: "\u5f53\u524d\u7d22\u5f15\uff1a",
  interactions: "\u76f8\u4e92\u4f5c\u7528",
  doseRules: "\u5242\u91cf\u89c4\u5219",
  doseCandidates: "\u5242\u91cf\u5019\u9009",
  overdoseWarnings: "\u8fc7\u91cf\u8b66\u544a",
  drugEffects: "\u836f\u6548 / \u4f5c\u7528\u673a\u5236",
  pharmacokinetics: "PK / \u836f\u4ee3\u7ebf\u7d22",
  enzymeRelations: "CYP / \u4ee3\u8c22\u9176\u5173\u7cfb",
  sources: "\u6765\u6e90\u6458\u8981",
  loading: "\u8bfb\u53d6\u8be6\u60c5\u4e2d...",
  error: "\u9519\u8bef",
  selected: "\u5df2\u9009\u62e9",
};

function apiCacheKey() {
  const counts = state.manifest?.counts || {};
  return [
    state.manifest?.dataset_version,
    state.manifest?.api_version,
    counts.substances,
    counts.interactions,
    counts.dose_rules,
    counts.dose_candidates,
    counts.overdose_warnings,
    counts.drug_effects,
    counts.pharmacokinetics,
    counts.enzyme_relations,
  ].filter(Boolean).join("-") || "boot";
}

function apiUrl(path, options = {}) {
  const cleanPath = String(path || "").replace(/^\/?api\//, "").replace(/^\//, "");
  const url = new URL(`api/${cleanPath}`, window.location.href);
  if (options.fresh) {
    url.searchParams.set("_ts", String(Date.now()));
  } else if (options.versioned !== false && cleanPath !== "manifest.json") {
    url.searchParams.set("_v", apiCacheKey());
  }
  return url.toString();
}

async function fetchJson(path, options = {}) {
  const cleanPath = String(path || "").replace(/^\/?api\//, "").replace(/^\//, "");
  const isManifest = cleanPath === "manifest.json";
  const fresh = Boolean(options.fresh || isManifest);
  const response = await fetch(apiUrl(path, { versioned: !isManifest, fresh }), { cache: fresh ? "no-store" : "no-cache" });
  if (!response.ok) throw new Error(`${ui.fetchFailed}: ${path} HTTP ${response.status}`);
  return response.json();
}

async function safeFetch(path, options = {}) {
  if (!path) return [];
  const expectedCount = Number(options.expectedCount || 0);
  try {
    const payload = await fetchJson(path, options);
    const rows = Array.isArray(payload) ? payload : payload ? [payload] : [];
    if (expectedCount > 0 && rows.length === 0 && !options.fresh) {
      return safeFetch(path, { ...options, fresh: true, expectedCount: 0 });
    }
    return rows;
  } catch {
    if (expectedCount > 0 && !options.fresh) {
      return safeFetch(path, { ...options, fresh: true, expectedCount: 0 });
    }
    return [];
  }
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString("zh-CN");
}

function formatValue(value, fallback = ui.unknown) {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function formatHours(value) {
  if (value === null || value === undefined || value === "") return ui.unknown;
  const numeric = Number(value);
  if (Number.isFinite(numeric)) return `${numeric.toFixed(2)} h`;
  return String(value);
}

function hasValue(value) {
  return value !== null && value !== undefined && value !== "";
}

function firstValue(...values) {
  return values.find(hasValue);
}

function firstPkValue(rows, keys) {
  for (const row of rows || []) {
    for (const key of keys) {
      if (hasValue(row?.[key])) return row[key];
    }
  }
  return undefined;
}

function formatMinutes(value) {
  if (!hasValue(value)) return ui.unknown;
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return String(value);
  if (numeric >= 60) return `${(numeric / 60).toFixed(1)} h`;
  return `${numeric.toFixed(0)} min`;
}

function mergePharmacokinetics(detail, overlayRows) {
  const rows = [];
  const seen = new Set();
  const add = (row) => {
    if (!row || typeof row !== "object") return;
    const key = row.fact_id || [row.source_name, row.source_tier, row.half_life_hours, row.onset_minutes, row.duration_minutes, row.standard_type].join("|");
    if (seen.has(key)) return;
    seen.add(key);
    rows.push(row);
  };
  (Array.isArray(detail?.pharmacokinetics) ? detail.pharmacokinetics : []).forEach(add);
  (Array.isArray(detail?.pharmacokinetics_detail) ? detail.pharmacokinetics_detail : []).forEach(add);
  (overlayRows || []).forEach(add);
  return rows;
}

function html(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#039;",
    '"': "&quot;",
  }[char]));
}

function normalizeText(value) {
  return String(value || "")
    .toLocaleLowerCase("zh-CN")
    .normalize("NFKC")
    .replace(/[\s_\-./()[\]{}]+/g, " ")
    .trim();
}

function compactText(value) {
  return normalizeText(value).replace(/\s+/g, "");
}

function searchShardKey(value) {
  const text = compactText(value);
  if (!text) return "other";
  const codePoint = text.codePointAt(0);
  const char = String.fromCodePoint(codePoint);
  if (/^[a-z0-9]$/i.test(char)) {
    const prefix = Array.from(text).filter((part) => /^[a-z0-9]$/i.test(part)).join("").slice(0, 2);
    return (prefix || char).toLocaleLowerCase("en-US");
  }
  return `u${codePoint.toString(16).padStart(4, "0")}`;
}

function searchShardKeysForQuery(query) {
  const normalized = normalizeText(query);
  const compact = compactText(query);
  const terms = [normalized, ...normalized.split(" ").filter(Boolean)];
  if (compact && compact !== normalized) terms.push(compact);
  if (compact && !/^[\x00-\x7F]+$/.test(compact)) {
    terms.push(...Array.from(compact).slice(0, 4));
  }
  const keys = [];
  const seen = new Set();
  for (const term of terms) {
    const key = searchShardKey(term);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    keys.push(key);
    if (keys.length >= 6) break;
  }
  return keys.length ? keys : ["other"];
}


function aliasesOf(item) {
  if (Array.isArray(item?.aliases)) return item.aliases.filter(Boolean).map(String);
  if (item?.aliases) return [String(item.aliases)];
  return [];
}

function haystack(item) {
  return normalizeText([
    item?.id,
    item?.name_zh,
    item?.name_en,
    item?.category,
    ...aliasesOf(item),
  ].filter(Boolean).join(" "));
}

function displayName(item) {
  return item?.name_zh || item?.name_en || item?.id || ui.unknownSubstance;
}

function subName(item) {
  const zh = item?.name_zh || "";
  const en = item?.name_en || "";
  if (zh && en && zh !== en) return en;
  return item?.id || "";
}

function setStatus(message, isError = false) {
  const line = $("statusLine");
  line.textContent = message;
  line.style.color = isError ? "var(--red)" : "var(--muted)";
}

function updateStats() {
  const counts = state.manifest?.counts || {};
  const substanceTotal = counts.substances || state.searchManifest?.items || state.searchIndex.length;
  $("substanceCount").textContent = formatNumber(substanceTotal);
  $("interactionCount").textContent = formatNumber(counts.interactions || 0);
  $("doseCount").textContent = formatNumber(counts.dose_rules || 0);
  $("candidateCount").textContent = formatNumber(counts.dose_candidates || 0);
  $("overdoseCount").textContent = formatNumber(counts.overdose_warnings || 0);
  $("effectCount").textContent = formatNumber(counts.drug_effects || 0);
  $("pkCount").textContent = formatNumber((counts.pharmacokinetics || 0) + (counts.enzyme_relations || 0));
  const sourceCount = state.manifest?.source_library?.sources_count
    || state.manifest?.online_library?.source_library?.sources_count
    || state.sourceIndex?.sources_count
    || 0;
  $("sourceCount").textContent = formatNumber(sourceCount);
  const packageBytes = state.manifest?.online_library?.full_package?.zip_bytes
    || state.manifest?.full_package?.zip_bytes
    || 0;
  const packageText = packageBytes ? ` \u00b7 \u5168\u91cf\u5305 ${(packageBytes / 1024 / 1024).toFixed(1)} MB` : "";
  $("apiMeta").textContent = `\u5df2\u52a0\u8f7d \u00b7 ${formatNumber(substanceTotal)} \u4e2a\u836f\u7269\u5b9e\u4f53 \u00b7 ${formatNumber(counts.interactions || 0)} \u6761\u76f8\u4e92\u4f5c\u7528 \u00b7 ${formatNumber(counts.drug_effects || 0)} \u6761\u836f\u6548/\u673a\u5236 \u00b7 ${formatNumber(counts.dose_candidates || 0)} \u6761\u5242\u91cf\u5019\u9009 \u00b7 ${formatNumber(counts.overdose_warnings || 0)} \u6761\u8fc7\u91cf\u8b66\u544a${packageText}`;
}

function scoreItem(item, query) {
  const q = normalizeText(query);
  const qCompact = compactText(query);
  if (!q) return 1;
  const id = normalizeText(item.id);
  const en = normalizeText(item.name_en);
  const zh = normalizeText(item.name_zh);
  const bag = haystack(item);
  const compactBag = compactText(bag);
  if (id === q || en === q || zh === q) return 100;
  if (compactText(id) === qCompact || compactText(en) === qCompact || compactText(zh) === qCompact) return 95;
  if (id.startsWith(q) || en.startsWith(q) || zh.startsWith(q)) return 80;
  if (bag.includes(q) || compactBag.includes(qCompact)) return 50;
  return 0;
}

async function fetchSearchShard(key) {
  const shardKey = key || "other";
  if (state.searchShardCache.has(shardKey)) return state.searchShardCache.get(shardKey);
  const knownCount = state.searchManifest?.shards?.[shardKey];
  if (state.searchManifest && !knownCount) {
    state.searchShardCache.set(shardKey, []);
    return [];
  }
  const template = state.searchManifest?.shard_path || "search/shards/{key}.json";
  const rows = await safeFetch(template.replace("{key}", encodeURIComponent(shardKey)));
  state.searchShardCache.set(shardKey, rows);
  return rows;
}


async function search(query) {
  const q = query.trim();
  if (!q) return [];
  const keys = searchShardKeysForQuery(q);
  const batches = await Promise.all(keys.map((key) => fetchSearchShard(key)));
  const byId = new Map();
  for (const rows of batches) {
    for (const item of rows) {
      if (item?.id) byId.set(item.id, item);
    }
  }
  return Array.from(byId.values())
    .map((item) => ({ item, score: scoreItem(item, q) }))
    .filter((row) => row.score > 0)
    .sort((a, b) => b.score - a.score || displayName(a.item).localeCompare(displayName(b.item), "zh-CN"))
    .slice(0, 80);
}

function renderSearchPrompt() {
  state.activeRows = [];
  const list = $("results");
  $("resultCount").textContent = "0 \u6761";
  list.className = "result-list empty";
  list.textContent = "\u8f93\u5165\u4e2d\u6587\u540d\u3001\u82f1\u6587\u540d\u3001\u522b\u540d\u6216 ID \u540e\u68c0\u7d22\uff1b\u9875\u9762\u4e0d\u4f1a\u518d\u6253\u5f00\u65f6\u52a0\u8f7d\u5168\u91cf\u7d22\u5f15\u3002";
  const total = state.searchManifest?.items || state.manifest?.counts?.substances || 0;
  setStatus(`\u5df2\u52a0\u8f7d API \u5143\u6570\u636e \u00b7 ${formatNumber(total)} \u4e2a\u5b9e\u4f53 \u00b7 \u641c\u7d22\u65f6\u6309\u5206\u7247\u8bfb\u53d6\u3002`);
}

function renderResultRows(rows = state.activeRows) {
  const list = $("results");
  $("resultCount").textContent = `${rows.length} \u6761`;
  if (!state.query.trim()) {
    renderSearchPrompt();
    return;
  }
  if (rows.length) {
    setStatus(`\u547d\u4e2d ${formatNumber(rows.length)} \u6761\u7ed3\u679c\uff0c\u9009\u62e9\u540e\u67e5\u770b\u8bc1\u636e\u3002`);
  } else {
    setStatus("\u672a\u547d\u4e2d\u3002\u53ef\u5c1d\u8bd5\u82f1\u6587\u901a\u7528\u540d\u3001\u4e2d\u6587\u540d\u3001RxNorm \u6216\u539f\u59cb ID\u3002", true);
  }
  if (!rows.length) {
    list.className = "result-list empty";
    list.textContent = "\u6682\u65e0\u7ed3\u679c";
    return;
  }
  list.className = "result-list";
  list.innerHTML = "";
  for (const { item } of rows) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `result-card ${item.id === state.activeId ? "active" : ""}`;
    const aliasText = aliasesOf(item).length ? `\u522b\u540d\uff1a${aliasesOf(item).slice(0, 5).join(" / ")}` : "";
    button.innerHTML = `
      <div class="card-head">
        <div>
          <div class="card-title">${html(displayName(item))}</div>
          <div class="card-meta">${html(subName(item))}</div>
        </div>
        <span class="badge">${html(item.category || "Drug")}</span>
      </div>
      ${aliasText ? `<div class="card-meta">${html(aliasText)}</div>` : ""}
    `;
    button.addEventListener("click", () => selectItem(item));
    list.appendChild(button);
  }
}

async function renderResults() {
  const token = ++state.renderToken;
  const q = state.query.trim();
  if (!q) {
    renderSearchPrompt();
    return [];
  }
  $("results").className = "result-list empty";
  $("results").textContent = "\u6b63\u5728\u8bfb\u53d6\u7d22\u5f15\u5206\u7247...";
  $("resultCount").textContent = "...";
  setStatus(`\u6b63\u5728\u6309\u5206\u7247\u68c0\u7d22\u300c${q}\u300d...`);
  const rows = await search(q);
  if (token !== state.renderToken) return [];
  state.activeRows = rows;
  renderResultRows(rows);
  return rows;
}

function scheduleRenderResults(delay = 120) {
  window.clearTimeout(state.searchDebounce);
  state.searchDebounce = window.setTimeout(() => {
    renderResults();
  }, delay);
}

async function findSearchItemById(id, preferredQuery = "") {
  const keys = searchShardKeysForQuery(preferredQuery || id);
  const batches = await Promise.all(keys.map((key) => fetchSearchShard(key)));
  for (const rows of batches) {
    const hit = rows.find((item) => item?.id === id);
    if (hit) return hit;
  }
  return null;
}

async function selectItem(item) {
  state.activeId = item.id;
  renderResultRows(state.activeRows);
  $("detailBadge").textContent = ui.loading;
  $("detail").className = "detail-card empty";
  $("detail").textContent = ui.loading;
  const paths = item.paths || {};
  try {
    const detail = await fetchJson(paths.substance);
    const detailPaths = { ...paths, ...(detail.paths || {}) };
    const [interactions, doseRules, doseCandidates, overdoseWarnings, drugEffects, pharmacokinetics, enzymeRelations] = await Promise.all([
      safeFetch(detailPaths.interactions, { expectedCount: detail.interaction_count || 0 }),
      safeFetch(detailPaths.dose_rules, { expectedCount: detail.dose_rule_count || 0 }),
      safeFetch(detailPaths.dose_candidates, { expectedCount: detail.dose_candidate_count || 0 }),
      safeFetch(detailPaths.overdose_warnings, { expectedCount: detail.overdose_warning_count || 0 }),
      safeFetch(detailPaths.drug_effects, { expectedCount: detail.drug_effect_count || 0 }),
      safeFetch(detailPaths.pharmacokinetics, { expectedCount: detail.pharmacokinetic_count || 0 }),
      safeFetch(detailPaths.enzyme_relations, { expectedCount: detail.enzyme_relation_count || 0 }),
    ]);
    renderDetail(detail, interactions, doseRules, doseCandidates, overdoseWarnings, drugEffects, mergePharmacokinetics(detail, pharmacokinetics), enzymeRelations);
    const params = new URLSearchParams(window.location.search);
    params.set("id", item.id);
    if (state.query) params.set("q", state.query);
    else params.delete("q");
    history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
  } catch (error) {
    $("detailBadge").textContent = ui.error;
    $("detail").className = "detail-card empty";
    $("detail").textContent = error.message || String(error);
  }
}

function renderDetail(detail, interactions, doseRules, doseCandidates, overdoseWarnings, drugEffects, pharmacokinetics, enzymeRelations) {
  $("detailBadge").textContent = detail.id || ui.selected;
  const sortedInteractions = [...interactions]
    .sort((a, b) => (riskRank[b.risk_level] || 0) - (riskRank[a.risk_level] || 0))
    .slice(0, 80);
  const sourceRows = Array.isArray(detail.source_summary) ? detail.source_summary.slice(0, 10) : [];
  const cyp = Array.isArray(detail.cyp_tags) && detail.cyp_tags.length ? detail.cyp_tags.join(" / ") : ui.unknown;
  const aliases = aliasesOf(detail).length ? aliasesOf(detail).join(" / ") : ui.unknown;
  const baseHalfLife = firstValue(detail.base_half_life, firstPkValue(pharmacokinetics, ["half_life_hours_mean", "half_life_hours"]));
  const baseOnset = firstValue(detail.base_onset, firstPkValue(pharmacokinetics, ["onset_minutes"]));
  const baseDuration = firstValue(detail.base_duration, firstPkValue(pharmacokinetics, ["duration_minutes"]));
  $("detail").className = "detail-card";
  $("detail").innerHTML = `
    <div class="detail-title">
      <h3>${html(displayName(detail))}</h3>
      <p>${html(subName(detail))}</p>
    </div>
    <div class="kv-grid">
      <div><span>${ui.category}</span><strong>${html(formatValue(detail.category, ui.unknown))}</strong></div>
      <div><span>${ui.solubility}</span><strong>${html(formatValue(detail.solubility))}</strong></div>
      <div><span>${ui.halfLife}</span><strong>${html(formatHours(baseHalfLife))}</strong></div>
      <div><span>${ui.onsetDuration}</span><strong>${html(`${formatMinutes(baseOnset)} / ${formatMinutes(baseDuration)}`)}</strong></div>
    </div>
    <section class="subsection">
      <h4>${ui.identity}</h4>
      <p class="card-meta">${ui.aliases}${html(aliases)}</p>
      <p class="card-meta">${ui.cyp}${html(cyp)}</p>
      <p class="card-meta">${ui.summary}${formatNumber(detail.drug_effect_count || drugEffects.length)} ${ui.drugEffects}\uff0c${formatNumber(detail.pharmacokinetic_count || pharmacokinetics.length)} ${ui.pharmacokinetics}\uff0c${formatNumber(detail.enzyme_relation_count || enzymeRelations.length)} ${ui.enzymeRelations}\uff0c${formatNumber(detail.interaction_count || sortedInteractions.length)} ${ui.interactions}\uff0c${formatNumber(detail.dose_rule_count || doseRules.length)} ${ui.doseRules}\uff0c${formatNumber(detail.dose_candidate_count || doseCandidates.length)} ${ui.doseCandidates}\uff0c${formatNumber(detail.overdose_warning_count || overdoseWarnings.length)} ${ui.overdoseWarnings}</p>
    </section>
    <section class="subsection">
      <h4>${ui.drugEffects} ${drugEffects.length}</h4>
      <div class="stack">${renderDrugEffects(drugEffects)}</div>
    </section>
    <section class="subsection">
      <h4>${ui.pharmacokinetics} ${pharmacokinetics.length}</h4>
      <div class="stack">${renderPharmacokinetics(pharmacokinetics)}</div>
    </section>
    <section class="subsection">
      <h4>${ui.enzymeRelations} ${enzymeRelations.length}</h4>
      <div class="stack">${renderEnzymeRelations(enzymeRelations)}</div>
    </section>
    <section class="subsection">
      <h4>${ui.overdoseWarnings} ${overdoseWarnings.length}</h4>
      <div class="stack">${renderOverdoseWarnings(overdoseWarnings)}</div>
    </section>
    <section class="subsection">
      <h4>${ui.doseCandidates} ${doseCandidates.length}</h4>
      <div class="stack">${renderDoseCandidates(doseCandidates)}</div>
    </section>
    <section class="subsection">
      <h4>${ui.doseRules} ${doseRules.length}</h4>
      <div class="stack">${renderDoseRules(doseRules)}</div>
    </section>
    <section class="subsection">
      <h4>${ui.interactions} Top ${sortedInteractions.length}</h4>
      <div class="stack">${renderInteractions(sortedInteractions)}</div>
    </section>
    <section class="subsection">
      <h4>${ui.sources} ${sourceRows.length}</h4>
      <div class="stack">${renderSources(sourceRows)}</div>
    </section>
  `;
}

function riskClass(risk) {
  return String(risk || "Unknown").toLocaleLowerCase("en-US").replace(/[^a-z0-9]+/g, "-");
}

function otherSubstance(row) {
  if (row.substance_a_id === state.activeId) {
    return row.substance_b_name || row.substance_b_name_en || row.substance_b_id;
  }
  return row.substance_a_name || row.substance_a_name_en || row.substance_a_id;
}

function sourceLink(row) {
  const href = safeHttpUrl(row.source_url);
  return href ? ` \u00b7 <a href="${html(href)}" target="_blank" rel="noopener noreferrer">\u6765\u6e90</a>` : "";
}

function renderDrugEffects(rows) {
  if (!rows.length) return '<div class="empty">\u6682\u65e0\u5df2\u7ed3\u6784\u5316\u7684\u836f\u6548\u3001\u9002\u5e94\u75c7\u6216\u4f5c\u7528\u673a\u5236\u8bb0\u5f55\u3002</div>';
  return rows.slice(0, 60).map((row) => {
    const title = row.mechanism_of_action ? "\u4f5c\u7528\u673a\u5236" : row.section || "\u836f\u6548\u8bc1\u636e";
    const body = row.mechanism_of_action || row.effect_text || row.evidence || "";
    const target = row.target ? `\u9776\u70b9\uff1a${html(row.target)}` : "";
    const action = row.action_type ? `\u4f5c\u7528\u7c7b\u578b\uff1a${html(row.action_type)}` : "";
    return `
      <article class="effect-card">
        <div class="card-head"><strong>${html(title)}</strong><span class="badge">${html(row.confidence || "Unknown")}</span></div>
        <div class="card-meta">${html(row.source_name || "Unknown source")} \u00b7 ${html(row.source_tier || "Unknown")}${sourceLink(row)}</div>
        ${target || action ? `<div class="card-meta">${[target, action].filter(Boolean).join(" \u00b7 ")}</div>` : ""}
        <div class="card-meta effect-text">${html(body || "\u65e0\u6587\u672c")}</div>
      </article>
    `;
  }).join("") + (rows.length > 60 ? `<div class="empty">\u4ec5\u663e\u793a\u524d 60 \u6761\uff0c\u5b8c\u6574\u8bb0\u5f55\u8bf7\u8bfb\u53d6\u5bf9\u5e94 drug_effects JSON\u3002</div>` : "");
}

function renderPharmacokinetics(rows) {
  if (!rows.length) return '<div class="empty">\u6682\u65e0\u5df2\u7ed3\u6784\u5316\u7684 PK \u8bb0\u5f55\u3002</div>';
  return rows.slice(0, 40).map((row) => {
    const values = [
      row.half_life_hours !== null && row.half_life_hours !== undefined ? `\u534a\u8870\u671f\uff1a${html(formatHours(row.half_life_hours))}` : "",
      hasValue(row.half_life_hours_upper) ? `\u4e0a\u9650\uff1a${html(formatHours(row.half_life_hours_upper))}` : "",
      hasValue(row.half_life_hours_mean) ? `\u5747\u503c\uff1a${html(formatHours(row.half_life_hours_mean))}` : "",
      hasValue(row.onset_minutes) ? `\u8d77\u6548\uff1a${html(formatMinutes(row.onset_minutes))}` : "",
      hasValue(row.duration_minutes) ? `\u6301\u7eed\uff1a${html(formatMinutes(row.duration_minutes))}` : "",
      row.route ? `\u9014\u5f84\uff1a${html(row.route)}` : "",
      row.standard_type ? `\u7c7b\u578b\uff1a${html(row.standard_type)}` : "",
      row.clearance ? `\u6e05\u9664\u7387\uff1a${html(row.clearance)}` : "",
      row.volume_distribution ? `Vd\uff1a${html(row.volume_distribution)}` : "",
      row.bioavailability ? `F\uff1a${html(row.bioavailability)}` : "",
    ].filter(Boolean).join(" \u00b7 ");
    return `
      <article class="pk-card">
        <div class="card-head"><strong>${html(row.standard_type || row.section || "PK")}</strong><span class="badge">${html(row.confidence || "Unknown")}</span></div>
        <div class="card-meta">${html(row.source_name || "Unknown source")} \u00b7 ${html(row.source_tier || "Unknown")}${sourceLink(row)}</div>
        ${values ? `<div class="card-meta">${values}</div>` : ""}
        ${row.text ? `<div class="card-meta">${html(row.text)}</div>` : ""}
      </article>
    `;
  }).join("") + (rows.length > 40 ? `<div class="empty">\u4ec5\u663e\u793a\u524d 40 \u6761 PK \u7ebf\u7d22\u3002</div>` : "");
}

function renderEnzymeRelations(rows) {
  if (!rows.length) return '<div class="empty">\u6682\u65e0 CYP / \u4ee3\u8c22\u9176\u5173\u7cfb\u8bb0\u5f55\u3002</div>';
  return rows.slice(0, 50).map((row) => {
    const title = row.tag || [row.enzyme, row.relation].filter(Boolean).join("_") || "enzyme_relation";
    return `
      <article class="pk-card enzyme">
        <div class="card-head"><strong>${html(title)}</strong><span class="badge">${html(row.confidence || "Unknown")}</span></div>
        <div class="card-meta">${html(row.source_name || "Unknown source")} \u00b7 ${html(row.source_tier || "Unknown")}${sourceLink(row)}</div>
        <div class="card-meta">${html([row.enzyme, row.relation].filter(Boolean).join(" / ") || row.text || "\u65e0\u6587\u672c")}</div>
        ${row.text ? `<div class="card-meta">${html(row.text)}</div>` : ""}
      </article>
    `;
  }).join("") + (rows.length > 50 ? `<div class="empty">\u4ec5\u663e\u793a\u524d 50 \u6761\u9176\u5173\u7cfb\u7ebf\u7d22\u3002</div>` : "");
}

function renderInteractions(rows) {
  if (!rows.length) return '<div class="empty">\u6682\u65e0\u7ed3\u6784\u5316\u76f8\u4e92\u4f5c\u7528\u8bb0\u5f55\u3002</div>';
  return rows.map((row) => {
    const risk = row.risk_level || "Unknown";
    return `
      <article class="interaction-card">
        <div class="card-head"><strong>${html(otherSubstance(row))}</strong><span class="badge ${html(riskClass(risk))}">${html(riskLabels[risk] || risk)}</span></div>
        <div class="card-meta">${html(row.interaction_type || "interaction")} \u00b7 ${html(row.source_tier || "Unknown")} \u00b7 ${html(row.confidence || "Unknown")}</div>
        ${row.action ? `<div class="card-meta">\u5904\u7f6e\uff1a${html(row.action)}</div>` : ""}
        ${row.mechanism ? `<div class="card-meta">\u673a\u5236\uff1a${html(row.mechanism)}</div>` : ""}
        ${row.note ? `<div class="card-meta">${html(row.note)}</div>` : ""}
      </article>
    `;
  }).join("");
}

function renderDoseRules(rows) {
  if (!rows.length) return '<div class="empty">\u6682\u65e0\u5df2\u5f52\u4e00\u5316\u7684\u786c\u9608\u503c\u5242\u91cf\u89c4\u5219\u3002</div>';
  return rows.map((rule) => {
    const thresholds = Array.isArray(rule.thresholds)
      ? rule.thresholds.map((item) => item.label || `${item.level || item.risk || ui.unknown}: ${item.limit ?? item.max ?? "?"} ${rule.unit || ""}`).join("\uff1b")
      : "";
    return `
      <article class="dose-card">
        <div class="card-head"><strong>${html(rule.rule_id || "dose_rule")}</strong><span class="badge">${html(rule.confidence || "Unknown")}</span></div>
        <div class="card-meta">\u9014\u5f84\uff1a${html(rule.route || ui.unknown)} \u00b7 \u7a97\u53e3\uff1a${html(rule.window_hours || "?")} h \u00b7 \u5355\u4f4d\uff1a${html(rule.unit || "?")}</div>
        <div class="card-meta">${html(thresholds || rule.note || "\u9608\u503c\u4fe1\u606f\u672a\u5b8c\u6574")}</div>
        ${rule.note ? `<div class="card-meta">\u6ce8\u91ca\uff1a${html(rule.note)}</div>` : ""}
        ${rule.source_name ? `<div class="card-meta">\u6765\u6e90\uff1a${html(rule.source_name)}</div>` : ""}
      </article>
    `;
  }).join("");
}

function renderDoseCandidates(rows) {
  if (!rows.length) return '<div class="empty">\u6682\u65e0\u5242\u91cf\u5019\u9009\u8bc1\u636e\u3002\u6ce8\u610f\uff1a\u5019\u9009\u4e0d\u7b49\u4e8e\u53ef\u76f4\u63a5\u62a5\u8b66\u7684\u5242\u91cf\u89c4\u5219\u3002</div>';
  return rows.slice(0, 120).map((row) => {
    const value = row.value_max ? `${row.value}-${row.value_max}` : row.value;
    return `
      <article class="dose-card candidate">
        <div class="card-head"><strong>${html(formatValue(value, "dose mention"))} ${html(row.unit || "")}</strong><span class="badge">${html(row.candidate_kind || "candidate")}</span></div>
        <div class="card-meta">${html(row.source_name || row.source_key || "Unknown source")} \u00b7 ${html(row.confidence || "Low")}</div>
        <div class="card-meta">${html(row.context || "\u65e0\u4e0a\u4e0b\u6587")}</div>
      </article>
    `;
  }).join("") + (rows.length > 120 ? `<div class="empty">\u4ec5\u663e\u793a\u524d 120 \u6761\uff0c\u5b8c\u6574\u8bb0\u5f55\u8bf7\u8bfb\u53d6\u5bf9\u5e94 dose_candidates JSON\u3002</div>` : "");
}

function renderOverdoseWarnings(rows) {
  if (!rows.length) return '<div class="empty">\u6682\u65e0\u8fc7\u91cf\u8b66\u544a\u6587\u672c\u3002</div>';
  return rows.slice(0, 40).map((row) => `
    <article class="dose-card overdose">
      <div class="card-head"><strong>${html(row.source_name || row.source_key || "Overdosage")}</strong><span class="badge major">${html(riskLabels[row.risk_level] || row.risk_level || "Major")}</span></div>
      <div class="card-meta">${html(row.source_tier || "Regulatory")} \u00b7 ${html(row.confidence || "Medium")}</div>
      <div class="card-meta">${html(row.text || "\u65e0\u6587\u672c")}</div>
    </article>
  `).join("") + (rows.length > 40 ? `<div class="empty">\u4ec5\u663e\u793a\u524d 40 \u6761\uff0c\u5b8c\u6574\u8bb0\u5f55\u8bf7\u8bfb\u53d6\u5bf9\u5e94 overdose_warnings JSON\u3002</div>` : "");
}

function safeHttpUrl(value) {
  try {
    const url = new URL(String(value || ""), window.location.href);
    if (url.protocol === "https:" || url.protocol === "http:") return url.toString();
  } catch {
    return "";
  }
  return "";
}

function renderSources(rows) {
  if (!rows.length) return '<div class="empty">\u6682\u65e0\u6765\u6e90\u6458\u8981\u3002</div>';
  return rows.map((row) => {
    const href = safeHttpUrl(row.source_url);
    const url = href ? `<a href="${html(href)}" target="_blank" rel="noopener noreferrer">\u6253\u5f00\u6765\u6e90</a>` : "";
    return `
      <article class="source-card">
        <div class="card-head"><strong>${html(row.source_name || "Unknown Source")}</strong><span class="badge">${html(row.source_tier || "Unknown")}</span></div>
        <div class="card-meta">\u7f6e\u4fe1\u5ea6\uff1a${html(row.confidence || "Unknown")} \u00b7 \u5ba1\u6838\uff1a${html(row.review_status || "unreviewed")} \u00b7 \u98ce\u9669\uff1a${html(row.risk_level || "Unknown")}</div>
        ${url ? `<div class="card-meta">${url}</div>` : ""}
      </article>
    `;
  }).join("");
}

function bindEvents() {
  $("searchInput").addEventListener("input", (event) => {
    state.query = event.target.value;
    scheduleRenderResults();
  });
  $("searchInput").addEventListener("keydown", async (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    window.clearTimeout(state.searchDebounce);
    const rows = await renderResults();
    const first = rows[0]?.item;
    if (first) selectItem(first);
  });
  $("clearSearch").addEventListener("click", () => {
    window.clearTimeout(state.searchDebounce);
    state.query = "";
    state.activeId = "";
    state.activeRows = [];
    $("searchInput").value = "";
    $("detailBadge").textContent = "\u672a\u9009\u62e9";
    $("detail").className = "detail-card empty";
    $("detail").textContent = "\u8bf7\u9009\u62e9\u836f\u7269\u67e5\u770b\u836f\u6548/\u673a\u5236\u3001PK \u7ebf\u7d22\u3001CYP \u5173\u7cfb\u3001\u76f8\u4e92\u4f5c\u7528\u3001\u5242\u91cf\u5019\u9009\u548c\u8fc7\u91cf\u8b66\u544a\u3002";
    history.replaceState(null, "", window.location.pathname);
    renderSearchPrompt();
  });
}

async function boot() {
  bindEvents();
  try {
    const [manifest, searchManifest, sources] = await Promise.all([
      fetchJson("manifest.json"),
      fetchJson("search/manifest.json").catch(() => null),
      fetchJson("sources/index.json").catch(() => null),
    ]);
    state.manifest = manifest;
    state.searchManifest = searchManifest;
    state.sourceIndex = sources;
    updateStats();
    const params = new URLSearchParams(window.location.search);
    const q = params.get("q") || "";
    const id = params.get("id") || "";
    state.query = q;
    $("searchInput").value = q;
    if (id) {
      const item = await findSearchItemById(id, q);
      if (q) await renderResults();
      else {
        state.activeRows = item ? [{ item, score: 100 }] : [];
        renderResultRows(state.activeRows);
      }
      if (item) await selectItem(item);
      else if (!q) renderSearchPrompt();
    } else if (q) {
      await renderResults();
    } else {
      renderSearchPrompt();
    }
  } catch (error) {
    setStatus(error.message || String(error), true);
    $("results").className = "result-list empty";
    $("results").textContent = "\u8bfb\u53d6 API \u5931\u8d25";
  }
}

boot();
