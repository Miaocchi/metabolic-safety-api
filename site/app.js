const state = {
  manifest: null,
  sourceIndex: null,
  searchIndex: [],
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
  Contraindicated: "禁忌",
  Dangerous: "危险",
  Unsafe: "不安全",
  Major: "严重",
  Moderate: "中度",
  Synergy: "协同/注意",
  Minor: "轻微",
  "Low Risk": "低风险",
  NoKnownClinicalSignificance: "无明确临床意义",
  Unknown: "未知",
};

function apiUrl(path) {
  const cleanPath = String(path || "").replace(/^\/?api\//, "").replace(/^\//, "");
  return new URL(`api/${cleanPath}`, window.location.href).toString();
}

async function fetchJson(path) {
  const cache = path === "manifest.json" ? "no-cache" : "force-cache";
  const response = await fetch(apiUrl(path), { cache });
  if (!response.ok) throw new Error(`读取 ${path} 失败：HTTP ${response.status}`);
  return response.json();
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString("zh-CN");
}

function formatValue(value, fallback = "未知") {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function formatHours(value) {
  if (value === null || value === undefined || value === "") return "未知";
  const numeric = Number(value);
  if (Number.isFinite(numeric)) return `${numeric.toFixed(2)} h`;
  return String(value);
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
  return item?.name_zh || item?.name_en || item?.id || "未命名药物";
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
  $("substanceCount").textContent = formatNumber(counts.substances || state.searchIndex.length);
  $("interactionCount").textContent = formatNumber(counts.interactions || 0);
  $("doseCount").textContent = formatNumber(counts.dose_rules || 0);
  const sourceCount = state.manifest?.source_library?.sources_count
    || state.manifest?.online_library?.source_library?.sources_count
    || state.sourceIndex?.sources_count
    || 0;
  $("sourceCount").textContent = formatNumber(sourceCount);
  const packageBytes = state.manifest?.online_library?.full_package?.zip_bytes
    || state.manifest?.full_package?.zip_bytes
    || 0;
  const packageText = packageBytes ? ` · 标准化融合包 ${(packageBytes / 1024 / 1024).toFixed(1)} MB` : "";
  $("apiMeta").textContent = `线上标准化融合库 · ${formatNumber(counts.substances || state.searchIndex.length)} 个药物实体 · ${formatNumber(counts.interactions || 0)} 条相互作用${packageText}`;
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

function search(query) {
  const q = query.trim();
  if (!q) return state.searchIndex.slice(0, 24).map((item) => ({ item, score: 1 }));
  return state.searchIndex
    .map((item) => ({ item, score: scoreItem(item, q) }))
    .filter((row) => row.score > 0)
    .sort((a, b) => b.score - a.score || displayName(a.item).localeCompare(displayName(b.item), "zh-CN"))
    .slice(0, 80);
}

function renderResults() {
  const rows = search(state.query);
  const list = $("results");
  $("resultCount").textContent = `${rows.length} 条`;
  if (!state.query.trim() && rows.length) {
    setStatus(`已载入 ${formatNumber(state.searchIndex.length)} 个线上药物实体。输入关键词后会在浏览器内检索。`);
  } else if (rows.length) {
    setStatus(`找到 ${formatNumber(rows.length)} 条候选，点击结果读取线上详情。`);
  } else {
    setStatus("线上索引未命中。可以尝试英文通用名、品牌名或 RxNorm/库内 ID。", true);
  }
  if (!rows.length) {
    list.className = "result-list empty";
    list.textContent = "没有匹配结果";
    return;
  }
  list.className = "result-list";
  list.innerHTML = "";
  for (const { item } of rows) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `result-card ${item.id === state.activeId ? "active" : ""}`;
    const aliasText = aliasesOf(item).length ? `别名：${aliasesOf(item).slice(0, 5).join(" / ")}` : "";
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

async function safeFetch(path) {
  if (!path) return [];
  try {
    const payload = await fetchJson(path);
    return Array.isArray(payload) ? payload : payload ? [payload] : [];
  } catch {
    return [];
  }
}

async function selectItem(item) {
  state.activeId = item.id;
  renderResults();
  $("detailBadge").textContent = "读取中";
  $("detail").className = "detail-card empty";
  $("detail").textContent = "正在读取线上详情...";
  const paths = item.paths || {};
  try {
    const [detail, interactions, doseRules] = await Promise.all([
      fetchJson(paths.substance),
      safeFetch(paths.interactions),
      safeFetch(paths.dose_rules),
    ]);
    renderDetail(detail, interactions, doseRules);
    const params = new URLSearchParams(window.location.search);
    params.set("id", item.id);
    if (state.query) params.set("q", state.query);
    else params.delete("q");
    history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
  } catch (error) {
    $("detailBadge").textContent = "失败";
    $("detail").className = "detail-card empty";
    $("detail").textContent = error.message || String(error);
  }
}

function renderDetail(detail, interactions, doseRules) {
  $("detailBadge").textContent = detail.id || "已选择";
  const sortedInteractions = [...interactions]
    .sort((a, b) => (riskRank[b.risk_level] || 0) - (riskRank[a.risk_level] || 0))
    .slice(0, 80);
  const sourceRows = Array.isArray(detail.source_summary) ? detail.source_summary.slice(0, 10) : [];
  const cyp = Array.isArray(detail.cyp_tags) && detail.cyp_tags.length ? detail.cyp_tags.join(" / ") : "未记录";
  const aliases = aliasesOf(detail).length ? aliasesOf(detail).join(" / ") : "未记录";
  $("detail").className = "detail-card";
  $("detail").innerHTML = `
    <div class="detail-title">
      <h3>${html(displayName(detail))}</h3>
      <p>${html(subName(detail))}</p>
    </div>
    <div class="kv-grid">
      <div><span>分类</span><strong>${html(formatValue(detail.category, "未分类"))}</strong></div>
      <div><span>溶解性</span><strong>${html(formatValue(detail.solubility))}</strong></div>
      <div><span>基础半衰期</span><strong>${html(formatHours(detail.base_half_life))}</strong></div>
      <div><span>起效 / 持续</span><strong>${html(`${formatValue(detail.base_onset, "?")} min / ${formatValue(detail.base_duration, "?")} min`)}</strong></div>
    </div>
    <section class="subsection">
      <h4>药理与检索信息</h4>
      <p class="card-meta">别名：${html(aliases)}</p>
      <p class="card-meta">CYP / 代谢标签：${html(cyp)}</p>
      <p class="card-meta">线上记录：${formatNumber(detail.interaction_count || sortedInteractions.length)} 条相互作用，${formatNumber(detail.dose_rule_count || doseRules.length)} 条剂量规则</p>
    </section>
    <section class="subsection">
      <h4>相互作用 Top ${sortedInteractions.length}</h4>
      <div class="stack">${renderInteractions(sortedInteractions)}</div>
    </section>
    <section class="subsection">
      <h4>剂量规则 ${doseRules.length}</h4>
      <div class="stack">${renderDoseRules(doseRules)}</div>
    </section>
    <section class="subsection">
      <h4>证据来源 ${sourceRows.length}</h4>
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

function renderInteractions(rows) {
  if (!rows.length) return '<div class="empty">线上库中没有找到该药物的相互作用记录。</div>';
  return rows.map((row) => {
    const risk = row.risk_level || "Unknown";
    return `
      <article class="interaction-card">
        <div class="card-head"><strong>${html(otherSubstance(row))}</strong><span class="badge ${html(riskClass(risk))}">${html(riskLabels[risk] || risk)}</span></div>
        <div class="card-meta">${html(row.interaction_type || "interaction")} · ${html(row.source_tier || "Unknown")} · ${html(row.confidence || "Unknown")}</div>
        ${row.action ? `<div class="card-meta">动作：${html(row.action)}</div>` : ""}
        ${row.mechanism ? `<div class="card-meta">机制：${html(row.mechanism)}</div>` : ""}
        ${row.note ? `<div class="card-meta">${html(row.note)}</div>` : ""}
      </article>
    `;
  }).join("");
}

function renderDoseRules(rows) {
  if (!rows.length) return '<div class="empty">线上库中没有找到结构化剂量上限规则。</div>';
  return rows.map((rule) => {
    const thresholds = Array.isArray(rule.thresholds)
      ? rule.thresholds.map((item) => item.label || `${item.level || item.risk || "阈值"}: ${item.limit ?? item.max ?? "?"} ${rule.unit || ""}`).join("；")
      : "";
    return `
      <article class="dose-card">
        <div class="card-head"><strong>${html(rule.rule_id || "dose_rule")}</strong><span class="badge">${html(rule.confidence || "Unknown")}</span></div>
        <div class="card-meta">途径：${html(rule.route || "未限定")} · 窗口：${html(rule.window_hours || "?")} h · 单位：${html(rule.unit || "?")}</div>
        <div class="card-meta">${html(thresholds || rule.note || "未提供阈值说明")}</div>
        ${rule.note ? `<div class="card-meta">说明：${html(rule.note)}</div>` : ""}
        ${rule.source_name ? `<div class="card-meta">来源：${html(rule.source_name)}</div>` : ""}
      </article>
    `;
  }).join("");
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
  if (!rows.length) return '<div class="empty">该记录暂未携带来源摘要。</div>';
  return rows.map((row) => {
    const href = safeHttpUrl(row.source_url);
    const url = href ? `<a href="${html(href)}" target="_blank" rel="noopener noreferrer">打开来源</a>` : "";
    return `
      <article class="source-card">
        <div class="card-head"><strong>${html(row.source_name || "Unknown Source")}</strong><span class="badge">${html(row.source_tier || "Unknown")}</span></div>
        <div class="card-meta">可信度：${html(row.confidence || "Unknown")} · 审核：${html(row.review_status || "unreviewed")} · 风险：${html(row.risk_level || "Unknown")}</div>
        ${url ? `<div class="card-meta">${url}</div>` : ""}
      </article>
    `;
  }).join("");
}

function bindEvents() {
  $("searchInput").addEventListener("input", (event) => {
    state.query = event.target.value;
    renderResults();
  });
  $("searchInput").addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    const first = search(state.query)[0]?.item;
    if (first) selectItem(first);
  });
  $("clearSearch").addEventListener("click", () => {
    state.query = "";
    state.activeId = "";
    $("searchInput").value = "";
    $("detailBadge").textContent = "未选择";
    $("detail").className = "detail-card empty";
    $("detail").textContent = "选择左侧药物后，会在线读取该药物的 PK 摘要、相互作用、剂量规则和证据来源。";
    history.replaceState(null, "", window.location.pathname);
    renderResults();
  });
}

async function boot() {
  bindEvents();
  try {
    const [manifest, index, sources] = await Promise.all([
      fetchJson("manifest.json"),
      fetchJson("search/index.json"),
      fetchJson("sources/index.json").catch(() => null),
    ]);
    state.manifest = manifest;
    state.searchIndex = Array.isArray(index) ? index : [];
    state.sourceIndex = sources;
    updateStats();
    const params = new URLSearchParams(window.location.search);
    const q = params.get("q") || "";
    const id = params.get("id") || "";
    state.query = q;
    $("searchInput").value = q;
    renderResults();
    if (id) {
      const item = state.searchIndex.find((row) => row.id === id);
      if (item) await selectItem(item);
    }
  } catch (error) {
    setStatus(error.message || String(error), true);
    $("results").className = "result-list empty";
    $("results").textContent = "线上 API 读取失败";
  }
}

boot();