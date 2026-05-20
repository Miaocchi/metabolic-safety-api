# 数据库提取现状与缺口对比

更新时间：2026-05-21  
数据快照：`D:\metabolic-safety-data\structured_parallel_all`，摘要更新时间 `2026-05-18T06:07:34Z`  
本地项目快照：`build/manifest.json` 与 `public/api/manifest.json`，dataset version `2026-05-18`  
远端 GitHub Pages API 快照：`https://miaocchi.github.io/metabolic-safety-api/api/manifest.json`，dataset version `2026-05-20`  
overlay 补齐时间：`2026-05-21`（新增 label-sections、safety-warnings、interaction-signals、food-interactions、adverse-signals、pgx 六个 overlay endpoint）

> 本文档用于回答：当前本地数据库已经提取出了什么、哪些内容已经进入当前 App Seed / Static API、以及对比原始数据库能力还缺少什么。

---

## 1. 结论摘要

当前已经形成了四层数据状态：

1. **结构化事实库已经很大**  
   `structured_parallel_all/structured_facts.sqlite` 已包含 openFDA、DailyMed、ChEMBL、FooDrugs、OnSIDES、PharmGKB 的批量 `EvidenceFact`，总量约 522 万条。

2. **当前离线 App Seed 仍然偏小**  
   `build/app_seed.sqlite` / `build/evidence_facts.json` 目前主要包含 DDInter 交互库和少量人工/在线抓取事实：
   - `evidence_facts`: 163,256
   - `interactions`: 160,235
   - `substances`: 2,286
   - `dose_rules`: 34

3. **本地 Static API 已经接入部分大库 overlay，但还不是完整事实浏览层**  
   本地 `public/api` 已从结构化大库导出：
   - `substances`: 119,875
   - `interactions`: 160,235
   - `dose_candidates`: 554,958
   - `overdose_warnings`: 76,572
   - `dose_rules`: 44,891

4. **远端 GitHub Pages API 已经比本地 `public/api` 更进一步；本分支已补齐下一次部署所需 overlay**  
   远端线上 `2026-05-20` 快照已登记 `drug-effects`、`enzyme-relations`、`pharmacokinetics` 三个内容 overlay，并把 `substances` 扩到 204,657。当前分支（2026-05-21）已在 exporter、Actions、PWA 和 Pages UI 中补齐 OnSIDES、FooDrugs、PharmGKB PGx、label sections / safety warnings / interaction signals；线上仍需等待下一次 workflow 部署。

主要缺口：

- App Seed 和 Static API 口径不一致：`dose_rules` 在 App Seed 中为 34，在 Static API 中为 44,891。
- 本地 `public/api` 落后远端 `2026-05-20`：缺 `enzyme-relations`、`pharmacokinetics` overlay；`drug-effects` 有 by-substance 文件但缺 manifest 和顶层登记。
- PharmGKB 的 PGx 事实已在本地结构化快照中存在，当前 CI `raw_sources.load_pharmgkb_bulk_facts` 已补齐 `pgx_relationship`、`pgx_clinical_annotation`、`pgx_drug_label`、`pgx_guideline` 抽取，并通过 `pgx/by-substance` 暴露给 PWA。
- FooDrugs / OnSIDES 已结构化为低可信信号，并已进入静态信号 API 与 PWA/Pages UI 的 evidence-only 展示边界；线上生产快照需下一次部署后更新。
- openFDA / DailyMed 的 `label_section`、`safety_warning`、`interaction_signal` 大量存在于结构化库，当前已作为独立 overlay endpoint 和 PWA/Pages evidence section 暴露；App Seed 仍保持精简，不承载百万级全文事实。
- ChEMBL 原始库中存在大量 half-life activity；当前代码的远端 CI 路径已能生成 `chembl_activities` PK facts，但本地 `structured_parallel_all` 快照中的 ChEMBL 分源仍没有 `pharmacokinetics`，说明本地快照需要重跑/同步。
- 剂量候选抽取仍有噪声，例如把肌酐清除率 `50 mL/minute` 一类上下文抽为 dose candidate，需要进一步区分“剂量值”和“实验室/肾功能阈值”。

### 2026-05-21 overlay 补齐

`tools/export_dose_overlay.py` 已扩展支持全部内容 overlay 类型，`build-public-api` CI 链路在 overlay 导出阶段同时写入以下新增 endpoint：

| 新增 endpoint | fact type(s) | 来源 |
|---|---|---|
| `label-sections/by-substance` | `label_section` | openFDA + DailyMed |
| `safety-warnings/by-substance` | `safety_warning` | openFDA + DailyMed |
| `interaction-signals/by-substance` | `interaction_signal` | openFDA + DailyMed |
| `food-interactions/by-substance` | `food_interaction` | FooDrugs |
| `adverse-signals/by-substance` | `adverse_event` | OnSIDES |
| `pgx/by-substance` | `pgx_relationship`, `pgx_clinical_annotation`, `pgx_drug_label`, `pgx_guideline` | PharmGKB |

顶层 `manifest.json` 现登记 `counts.label_sections`、`counts.safety_warnings`、`counts.interaction_signals`、`counts.food_interactions`、`counts.adverse_signals`、`counts.pgx`，以及对应的 `paths.*_by_substance` 和 overlay key（`label_section_overlay` 等）。

PGx 合并了 PharmGKB 四种 fact type（`pgx_relationship`、`pgx_clinical_annotation`、`pgx_drug_label`、`pgx_guideline`）为统一 `pgx/by-substance` endpoint。FooDrugs `food_interaction` 同时按 drug 与 food/bioactive subject 暴露，但 manifest records 按唯一 `fact_id` 去重。

安全语义不变：Unknown 不等于安全；Low confidence / Signal / Community 不能覆盖或降级 Regulatory / Guideline / CuratedDB；FooDrugs/OnSIDES 仅补盲/审阅线索；PGx 不生成个体化处方建议。

---


## 2. 当前输出产物对比

### 2.1 结构化事实库

位置：

```text
D:\metabolic-safety-data\structured_parallel_all\structured_facts.sqlite
/mnt/d/metabolic-safety-data/structured_parallel_all/structured_facts.sqlite
```

来源统计：

| source | facts | 当前定位 |
|---|---:|---|
| openFDA Label | 2,187,652 | 监管标签事实层 |
| OnSIDES | 1,209,425 | 不良事件候选信号层 |
| FooDrugs | 1,108,327 | 食物-药物相互作用候选信号层 |
| DailyMed SPL | 611,726 | 监管 SPL 标签事实层 |
| ChEMBL | 56,605 | 化合物身份、机制/target 层 |
| PharmGKB | 47,018 | PGx / 指南 / 标签证据层 |

fact type 统计：

| fact_type | facts | 说明 |
|---|---:|---|
| adverse_event | 1,209,425 | OnSIDES 不良事件信号 |
| food_interaction | 1,108,327 | FooDrugs 食物-药物候选相互作用 |
| label_section | 1,014,845 | openFDA / DailyMed 标签段落 |
| dose_candidate | 554,958 | 标签剂量文本候选 |
| substance_identity | 471,025 | 药物/物质身份候选 |
| drug_effect | 277,352 | 适应症、机制、作用文本 |
| safety_warning | 276,656 | 标签安全警告 |
| enzyme_relation | 78,120 | CYP / enzyme / transporter 相关文本关系 |
| overdose_warning | 76,572 | 过量警告段落 |
| interaction_signal | 67,102 | 标签相互作用文本信号 |
| pharmacokinetics | 44,621 | PK 文本事实 |
| pgx_relationship | 32,906 | PharmGKB gene-drug relationship |
| pgx_clinical_annotation | 7,090 | PharmGKB clinical annotation |
| pgx_drug_label | 1,381 | PharmGKB drug label |
| pgx_guideline | 373 | PharmGKB guideline |

### 2.2 当前 App Seed / 本地 seed 数据库

位置：

```text
build/app_seed.sqlite
build/evidence_facts.json
build/init_substances.json
build/init_interactions.json
build/init_dose_rules.json
```

manifest：

| 项 | 数量 |
|---|---:|
| evidence_facts | 163,256 |
| substances | 2,286 |
| interactions | 160,235 |
| dose_rules | 34 |

`build/evidence_facts.json` 按 fact type：

| fact_type | 数量 | 说明 |
|---|---:|---|
| drug_interaction | 160,235 | 主要来自 DDInter |
| substance_identity | 2,405 | DDInter alias、openFDA/RxNav/ChEMBL 等小规模身份事实 |
| source_text | 522 | openFDA / DailyMed 小规模标签文本 |
| pharmacokinetics | 58 | 主要是 PsychonautWiki / literature 小规模事实 |
| dose_rule | 34 | 人工/自动小规模剂量规则 |
| enzyme_relation | 2 | 小规模文学/绿茶儿茶素相关事实 |

按 source name：

| source | facts | 说明 |
|---|---:|---|
| DDInter 2.0 | 160,235 | 当前核心 DDI 库 |
| DDInter 2.0 + local zh aliases | 1,939 | 中文别名/身份映射 |
| openFDA drug label | 526 | 小规模标签事实，不是 bulk 全量 |
| RxNav / RxNorm | 187 | 实体归一化/RxCUI 映射 |
| ChEMBL | 145 | 小规模化合物身份事实 |
| PsychonautWiki GraphQL | 106 | 社区剂量/PK 候选，低可信 |
| DailyMed SPL | 78 | 小规模 SPL 文本事实 |
| openFDA drug label auto dose normalizer | 24 | 小规模 dose_rule |
| 其他人工/文献/监管 seed | 1 条级别 | FDA caffeine、acetaminophen、EFSA green tea 等 |

结论：**App Seed 当前主要是 DDInter 交互库 + 少量 seed facts，不是全部结构化大库。**

### 2.3 当前 Static API

位置：

```text
public/api
```

manifest：

| 项 | 数量 |
|---|---:|
| substances | 119,875 |
| interactions | 160,235 |
| dose_candidates | 554,958 |
| overdose_warnings | 76,572 |
| dose_rules | 44,891 |

Static API 额外观察：

- `dose-candidates/manifest.json` 来自 `D:\metabolic-safety-data\structured_parallel_all\structured_facts.sqlite`。
- `dose-rules/manifest.json` 显示：
  - `source_facts`: 631,530
  - `subjects_with_dose_rules`: 87,270
  - `unique_dose_rules`: 44,891
- `overdose-warnings/manifest.json` 显示：
  - `substances_with_dose_candidates`: 68,125
  - `substances_with_overdose_warnings`: 63,162
- `drug-effects/by-substance` 目录存在，约 100,675 个 substance 文件，但顶层 manifest 目前没有单列其总数。
- `sources/index.json` 仍是 App Seed 级别的 163,256 facts source summary，不代表 bulk structured DB 全量来源。

结论：**本地 Static API 已经把大库中的剂量候选、过量警告、自动剂量规则、物质索引和 drug effects 部分暴露出来，但本地 manifest 尚未登记 drug effects，也缺 PK、enzyme、PGx、safety warning、label section、signal 层的完整 endpoint 设计。**

### 2.4 远端 GitHub Pages Static API（2026-05-20）

真实 API manifest 位于：

```text
https://miaocchi.github.io/metabolic-safety-api/api/manifest.json
```

注意：`https://miaocchi.github.io/metabolic-safety-api/` 是 UI 根页面，不是 API 根；API 路径需要 `/api/...` 前缀。

远端 manifest：

| 项 | 数量 |
|---|---:|
| substances | 204,657 |
| interactions | 160,235 |
| dose_candidates | 727,971 |
| overdose_warnings | 74,198 |
| dose_rules | 46,723 |
| drug_effects | 162,368 |
| enzyme_relations | 111,328 |
| pharmacokinetics | 52,670 |
| adverse_signals.items | 0 |

远端已登记的新增 overlay：

| endpoint manifest | records | subjects | max_per_substance | 说明 |
|---|---:|---:|---:|---|
| `api/drug-effects/manifest.json` | 162,368 | 89,549 | 24 | label indications / purpose / pharmacodynamics / ChEMBL mechanism snippets |
| `api/enzyme-relations/manifest.json` | 111,328 | 22,642 | 24 | CYP / transporter relation evidence snippets |
| `api/pharmacokinetics/manifest.json` | 52,670 | 45,520 | 24 | PK structured values and label excerpts |

远端 full package：

| 项 | 值 |
|---|---|
| manifest | `api/packages/full/manifest.json` |
| zip | `api/packages/full/fused-online-library.zip` |
| zip bytes | 21,509,034 |
| zip sha256 | `2a4dcf695331bbefa4f18689576d3b6835116d592bed292a7cb93da40b8d310c` |
| source_library.facts_count | 244,284 |
| source_library.sources_count | 28 |

远端相对本地 `public/api` 的主要变化：

| 项 | 本地 2026-05-18 | 远端 2026-05-20 | 差异 |
|---|---:|---:|---:|
| substances | 119,875 | 204,657 | +84,782 |
| interactions | 160,235 | 160,235 | 0 |
| dose_candidates | 554,958 | 727,971 | +173,013 |
| overdose_warnings | 76,572 | 74,198 | -2,374 |
| dose_rules | 44,891 | 46,723 | +1,832 |
| drug_effects | 本地未登记 | 162,368 | 远端已登记 |
| enzyme_relations | 无 | 111,328 | 远端已新增 |
| pharmacokinetics | 无 | 52,670 | 远端已新增 |
| source_library facts | 163,256 | 244,284 | +81,028 |

远端 `2026-05-20` 快照时仍未解决的缺口（已于 2026-05-21 通过 overlay 导出补齐）：

- ~~`adverse_signals.items` 仍为 0，`api/adverse_signals/manifest.json` 不存在；OnSIDES `adverse_event` 尚未静态暴露。~~ → 已新增 `adverse-signals/by-substance` endpoint。
- ~~无 FooDrugs `food-interactions` endpoint。~~ → 已新增 `food-interactions/by-substance` endpoint。
- ~~无 PharmGKB PGx endpoint。~~ → 已新增 `pgx/by-substance` endpoint，合并 `pgx_relationship`、`pgx_clinical_annotation`、`pgx_drug_label`、`pgx_guideline`。
- ~~无 `label-sections`、`safety-warnings`、`interaction-signals` endpoint。~~ → 已新增三个 endpoint。

---

## 2.5 GitHub Actions / CI 事实生成链路

主远端构建 workflow：

```text
.github/workflows/build-data-api.yml
```

触发方式：

- `workflow_dispatch`
- 每周 schedule：`23 19 * * 0`
- push 到 `data/**`、`src/**`、`tests/**`、`pyproject.toml`、workflow、`site/**`、`tools/**`

关键环境变量：

```text
ALL_BULK_SOURCES=openfda_label,dailymed,chembl,foodrugs,onsides,pharmgkb
raw_max_records default=0       # 0 表示 full source
raw_stream_max_parts default=0  # 0 表示 all upstream parts
```

CI 分两段：

### A. source-layer-cache matrix

对每个 source 单独运行：

```text
python -m metabolic_safety_etl.cli remote-manifests \
  --sources "${source}" \
  --out "${RUNNER_TEMP}/manifests/${source}.json"

python -m metabolic_safety_etl.cli build-remote-source-facts \
  --sources "${source}" \
  --out ".cache/metabolic-source-facts/${source}/evidence_facts.json" \
  --summary-out ".cache/metabolic-source-facts/${source}/summary.json" \
  --temp-dir "${RUNNER_TEMP}/metabolic-raw-stream/${source}" \
  --raw-max-records "${RAW_MAX_RECORDS}" \
  --raw-stream-max-parts "${RAW_STREAM_MAX_PARTS}"
```

cache key 包含：

- upstream manifest fingerprint
- `src/metabolic_safety_etl/**/*.py` 和 `pyproject.toml` hash
- `RAW_MAX_RECORDS`
- `RAW_STREAM_MAX_PARTS`

这一步通过 `src/metabolic_safety_etl/raw_sources.py` 的 `write_remote_raw_source_facts_json()` 流式下载一个 part、解析为 `EvidenceFact` JSON、删除 raw part，避免在 CI runner 保留完整 raw mirror。

### B. build-and-deploy

先恢复全部六个 source layer：

```text
.cache/metabolic-source-facts/openfda_label/evidence_facts.json
.cache/metabolic-source-facts/dailymed/evidence_facts.json
.cache/metabolic-source-facts/chembl/evidence_facts.json
.cache/metabolic-source-facts/foodrugs/evidence_facts.json
.cache/metabolic-source-facts/onsides/evidence_facts.json
.cache/metabolic-source-facts/pharmgkb/evidence_facts.json
```

然后构建 base seed + base static API：

```text
python -m metabolic_safety_etl.cli build-public-api \
  --ddinter-dir data/raw/ddinter \
  --out build \
  --api-out public/api \
  --skip-raw-sources \
  --max-public-terms 120 \
  --public-limit 2 \
  --public-workers 8 \
  --psychonautwiki-pages 3 \
  --extra-facts data/optional \
  --extra-facts data/overrides \
  --extra-facts .cache/metabolic-source-facts/chembl/evidence_facts.json \
  --extra-facts .cache/metabolic-source-facts/pharmgkb/evidence_facts.json
```

这里有一个重要边界：

- `build-public-api` 的 base seed 只把 **ChEMBL** 与 **PharmGKB** source layer 作为 `--extra-facts` 注入 seed。
- openFDA / DailyMed / FooDrugs / OnSIDES 太大，不在这一步加载进 fused seed，而是在下一步流式写入 overlay。

最后流式导出 overlays：

```text
python tools/export_dose_overlay.py \
  --api-dir public/api \
  --max-content-per-substance 24 \
  --fact-json .cache/metabolic-source-facts/openfda_label/evidence_facts.json \
  --fact-json .cache/metabolic-source-facts/dailymed/evidence_facts.json \
  --fact-json .cache/metabolic-source-facts/chembl/evidence_facts.json \
  --fact-json .cache/metabolic-source-facts/foodrugs/evidence_facts.json \
  --fact-json .cache/metabolic-source-facts/onsides/evidence_facts.json \
  --fact-json .cache/metabolic-source-facts/pharmgkb/evidence_facts.json
```

`tools/export_dose_overlay.py` 当前会导出：

| overlay | 输入 fact types | 输出 |
|---|---|---|
| dose candidates | `dose_candidate` | `dose-candidates/by-substance`, `dose-candidates/manifest.json` |
| overdose warnings | `overdose_warning` | `overdose-warnings/by-substance`, `overdose-warnings/manifest.json` |
| generated dose rules | `dose_candidate`, `overdose_warning` | `dose-rules/by-substance`, `dose-rules/manifest.json` |
| drug effects | `drug_effect` | `drug-effects/by-substance`, `drug-effects/manifest.json` |
| pharmacokinetics | `pharmacokinetics` | `pharmacokinetics/by-substance`, `pharmacokinetics/manifest.json` |
| enzyme relations | `enzyme_relation` | `enzyme-relations/by-substance`, `enzyme-relations/manifest.json` |
| label sections | `label_section` | `label-sections/by-substance`, `label-sections/manifest.json` |
| safety warnings | `safety_warning` | `safety-warnings/by-substance`, `safety-warnings/manifest.json` |
| interaction signals | `interaction_signal` | `interaction-signals/by-substance`, `interaction-signals/manifest.json` |
| food interactions | `food_interaction` | `food-interactions/by-substance`, `food-interactions/manifest.json` |
| adverse signals | `adverse_event` | `adverse-signals/by-substance`, `adverse-signals/manifest.json` |
| PGx | `pgx_relationship`, `pgx_clinical_annotation`, `pgx_drug_label`, `pgx_guideline` | `pgx/by-substance`, `pgx/manifest.json` |

每个 content overlay 的 `--max-content-per-substance` 默认为 24，可通过 `--max-content-per-substance 0` 导出全部。

并更新顶层 `public/api/manifest.json`：

- `counts.dose_candidates`, `counts.overdose_warnings`, `counts.dose_rules`
- `counts.drug_effects`, `counts.pharmacokinetics`, `counts.enzyme_relations`
- `counts.label_sections`, `counts.safety_warnings`, `counts.interaction_signals`
- `counts.food_interactions`, `counts.adverse_signals`, `counts.pgx`
- `paths.*_by_substance`
- `dose_candidate_overlay`, `overdose_warning_overlay`, `dose_rule_overlay`
- `drug_effect_overlay`, `pharmacokinetics_overlay`, `enzyme_relation_overlay`
- `label_section_overlay`, `safety_warning_overlay`, `interaction_signal_overlay`
- `food_interaction_overlay`, `adverse_signal_overlay`, `pgx_overlay`
- `search_overlay`

部署步骤：复制 `site/.` 到 `public/`，再通过 `actions/upload-pages-artifact` + `actions/deploy-pages` 发布。

补充：`.github/workflows/build-data-api-cloudflare-pages.yml` 是较轻量 Cloudflare Pages 构建，主要运行 `build-public-api`，不是当前 GitHub Pages 远端 `2026-05-20` 大规模 bulk API 的主链路。

---

## 3. 各数据库：已提取内容 vs 缺少内容

## 3.1 DDInter

原始位置：

```text
D:\metabolic-safety-data\raw\ddinter
```

### 已提取

当前 DDInter 已经是项目核心交互库：

| 输出位置 | 内容 | 数量 |
|---|---|---:|
| `build/init_interactions.json` | DDI pairwise interactions | 160,235 |
| `build/evidence_facts.json` | `drug_interaction` facts | 160,235 |
| `public/api/interactions/by-substance` | 按物质分片的 interactions | 160,235 |
| `build/init_substances.json` | 部分 DDInter 物质与别名 | 2,286 app seed substances |

已使用字段：

- `Drug_A`
- `Drug_B`
- `Level`
- `DDInterID_A`
- `DDInterID_B`

当前 risk 映射：

| Level | 当前用途 |
|---|---|
| Major | 强交互风险提示 / avoid_or_modify_therapy |
| Moderate | 中等交互提示 |
| Minor | 轻度交互提示 |
| Unknown | candidate signal，不应视为安全 |

### 缺少 / 待补

| 缺口 | 影响 | 建议 |
|---|---|---|
| 机制字段不足 | 只能提示存在交互，不能解释 CYP/PK/PD 机制 | 用 openFDA / DailyMed `interaction_signal`、`enzyme_relation` 回填解释 |
| 人群/剂量/路线上下文不足 | 无法判断特定人群是否更高风险 | 保持为 pairwise risk，不做个体化处方建议 |
| 与 RxNorm / 标签名归一仍有限 | 搜索和合并可能出现重复 substance | 强化 RxNav、openFDA active ingredient、DailyMed SPL 的 canonical merge |
| Unknown 被误解为 safe 的风险 | 会降低安全边界 | UI 明确 `Unknown != safe` |

优先级：**最高**。继续作为核心 DDI 主库。

---

## 3.2 openFDA Drug Label

原始位置：

```text
D:\metabolic-safety-data\raw\openfda_label
```

结构化输出：

```text
D:\metabolic-safety-data\structured_parallel_all\_source_parts\openfda_label\structured_facts.sqlite
D:\metabolic-safety-data\structured_parallel_all\jsonl\openfda_label.jsonl
```

### 已提取到结构化大库

| fact_type | 数量 | 已提取内容 |
|---|---:|---|
| label_section | 806,986 | 标签段落，例如 dosage、warnings、clinical pharmacology 等 |
| dose_candidate | 487,118 | 剂量文本候选 |
| substance_identity | 258,058 | 药品/成分/品牌/产品身份 |
| safety_warning | 208,834 | 警告、禁忌、注意事项等文本 |
| drug_effect | 208,204 | 适应症、作用、机制相关段落 |
| enzyme_relation | 67,606 | CYP / enzyme / transporter 相关文本关系 |
| overdose_warning | 60,022 | 过量警告段落 |
| interaction_signal | 52,653 | 标签相互作用段落候选 |
| pharmacokinetics | 38,171 | PK 文本事实，如 half-life、metabolism、excretion 等 |

### 已进入当前 App Seed / Static API

| 目标 | 当前状态 |
|---|---|
| App Seed | 仅有小规模 `openFDA drug label` 526 facts，另有 `openFDA drug label auto dose normalizer` 24 dose rules |
| Static API dose candidates | 已导出 554,958 总 dose candidates，其中 openFDA 占 487,118 |
| Static API overdose warnings | 已导出 76,572 总 overdose warnings，其中 openFDA 占 60,022 |
| Static API dose rules | 已生成 44,891 unique dose rules，主要由 dose candidates / overdose warnings 支持 |
| Static API drug effects | 已有 `drug-effects/by-substance` 目录，但顶层 manifest 未列总数和来源分解 |

### 缺少 / 待补

> **2026-05-21 状态**：`label_section`、`safety_warning`、`pharmacokinetics`、`enzyme_relation`、`interaction_signal` 均已通过 `tools/export_dose_overlay.py` 导出为独立 overlay endpoint。以下为剩余缺口。

| 缺口 | 影响 | 建议 |
|---|---|---|
| ~~`label_section` 未完整暴露为 evidence endpoint~~ | ✅ 已新增 `label-sections/by-substance` | PWA 与 Pages UI 已接入 evidence-only 展示 |
| ~~`safety_warning` 未单独暴露~~ | ✅ 已新增 `safety-warnings/by-substance` | PWA 与 Pages UI 已接入，保留 machine-extraction disclaimer |
| ~~`pharmacokinetics` 未进入 Static API PK endpoint~~ | ✅ 已新增 `pharmacokinetics/by-substance` | — |
| ~~`enzyme_relation` 未进入风险解释层~~ | ✅ 已新增 `enzyme-relations/by-substance` | risk-service 融合待增强 |
| ~~`interaction_signal` 未用于 DDInter 解释~~ | ✅ 已新增 `interaction-signals/by-substance` | DDInter 解释融合待增强 |
| dose candidate 噪声 | 可能把 `50 mL/minute` 肌酐清除率阈值当作剂量 | dose parser 区分 dose amount、frequency、renal threshold、lab/PK threshold |
| App Seed 与 Static API 口径差异大 | 离线与在线体验不一致 | 明确 offline seed 是精简库，或将高优先级 rules 同步入 seed |

优先级：**最高**。openFDA 是监管标签主来源。

---

## 3.3 DailyMed SPL

原始位置：

```text
D:\metabolic-safety-data\raw\dailymed_spl
```

结构化输出：

```text
D:\metabolic-safety-data\structured_parallel_all\_source_parts\dailymed\structured_facts.sqlite
D:\metabolic-safety-data\structured_parallel_all\jsonl\dailymed.jsonl
```

### 已提取到结构化大库

| fact_type | 数量 | 已提取内容 |
|---|---:|---|
| label_section | 207,859 | SPL 标签段落 |
| substance_identity | 158,585 | SPL 药品/成分身份 |
| dose_candidate | 67,840 | 剂量候选文本 |
| safety_warning | 67,822 | 安全警告文本 |
| drug_effect | 61,657 | 适应症/作用文本 |
| overdose_warning | 16,550 | 过量警告 |
| interaction_signal | 14,449 | 相互作用段落候选 |
| enzyme_relation | 10,514 | CYP / enzyme 关系候选 |
| pharmacokinetics | 6,450 | PK 文本事实 |

### 已进入当前 App Seed / Static API

| 目标 | 当前状态 |
|---|---|
| App Seed | 仅有 78 条 `DailyMed SPL` source_text seed facts |
| Static API dose candidates / overdose warnings / dose rules | DailyMed 贡献已混入 overlay，但没有来源分解 manifest |
| Static API label evidence | 未看到完整 SPL label section endpoint |

### 缺少 / 待补

> **2026-05-21 状态**：SPL label sections、safety warnings、interaction signals、PK、enzyme 均已通过 overlay 导出覆盖 DailyMed 数据。以下为剩余缺口。

| 缺口 | 影响 | 建议 |
|---|---|---|
| ~~SPL 原文段落未完整进入 PWA evidence drawer~~ | ✅ 已新增 `label-sections/by-substance` 覆盖 DailyMed | PWA 与 Pages UI 已接入 evidence-only 展示 |
| openFDA 与 DailyMed 同药标签未去重/对齐 | 同一药物多产品多标签导致重复 | 按 active ingredient、route、dosage form、RxCUI 合并 |
| ~~DailyMed PK/CYP 未进入代谢解释层~~ | ✅ 已新增 `pharmacokinetics`、`enzyme-relations` overlay 覆盖 DailyMed | — |
| 剂量候选未区分 route/population | 儿童/成人/肾功能剂量可能混淆 | 在 dose rule 中保留 population、route、review_status |

优先级：**最高**。DailyMed 是 openFDA 的监管标签互补来源。

---

## 3.4 ChEMBL

原始位置：

```text
D:\metabolic-safety-data\raw\chembl
D:\metabolic-safety-data\raw\chembl\_extracted\chembl_36.db
```

结构化输出：

```text
D:\metabolic-safety-data\structured_parallel_all\_source_parts\chembl\structured_facts.sqlite
D:\metabolic-safety-data\structured_parallel_all\jsonl\chembl.jsonl
```

### 已提取到结构化大库

| fact_type | 数量 | 已提取内容 |
|---|---:|---|
| substance_identity | 49,114 | ChEMBL ID、preferred name、synonyms、部分化学属性 |
| drug_effect | 7,491 | target / mechanism / action 相关事实 |

当前 ChEMBL 结构化输出没有：

```text
pharmacokinetics: 0
```

### 已进入当前 App Seed / Static API

| 目标 | 当前状态 |
|---|---|
| App Seed | 仅有 145 条 ChEMBL substance identity seed facts |
| Static API substances | 结构化 identity 可能参与大规模 substance index，但来源分解不清晰 |
| Static API drug effects | 有 `drug-effects/by-substance`，但需要确认 ChEMBL 机制事实覆盖程度 |

### 原始库中发现但尚未结构化的内容

ChEMBL 原始 SQLite 已发现 half-life activity 潜力：

| activity 类型 | 数量 |
|---|---:|
| `T1/2` + `hr` | 88,876 |
| `Half duration` + `min` | 59 |
| `Plasma half life` + `min` | 8 |
| `Plasma half-life` + `hr` | 4 |
| `Terminal elimination t1/2` + `hr` | 1 |

### 缺少 / 待补

| 缺口 | 影响 | 建议 |
|---|---|---|
| half-life activity 未进入 `pharmacokinetics` | PK 解释少了大量文献/实验数据 | 新增 ChEMBL activity -> PK fact 抽取 |
| assay context 未标准化 | 体外/动物/人体数据可能混用 | claim_json 保留 assay、species、document、confidence |
| 化学属性没有独立 endpoint | ALogP、MW 等无法用于代谢/安全解释 | 增加 `chemical-properties/by-substance` 或并入 substance detail |
| mechanism/target 未完整进入 PWA | PD 解释能力不足 | 将 ChEMBL `drug_effect` 作为机制证据层展示 |

优先级：**中高**。identity / mechanism 可先用，half-life 抽取是重要增强任务。

---

## 3.5 PharmGKB / ClinPGx

原始位置：

```text
D:\metabolic-safety-data\raw\pharmgkb
```

结构化输出：

```text
D:\metabolic-safety-data\structured_parallel_all\_source_parts\pharmgkb\structured_facts.sqlite
D:\metabolic-safety-data\structured_parallel_all\jsonl\pharmgkb.jsonl
```

### 已提取到结构化大库

| fact_type | 数量 | 已提取内容 |
|---|---:|---|
| pgx_relationship | 32,906 | gene-drug / variant-drug 关系 |
| pgx_clinical_annotation | 7,090 | 临床注释与证据等级 |
| substance_identity | 5,268 | PharmGKB chemical identity |
| pgx_drug_label | 1,381 | PGx drug label 事实 |
| pgx_guideline | 373 | PGx guideline / CPIC 等指南信息 |

### 已进入当前 App Seed / Static API

旧快照中没有看到 PharmGKB 进入：

- `build/evidence_facts.json` source summary
- `public/api/sources/index.json`
- 顶层 `public/api/manifest.json`
- 独立 PGx endpoint

当前分支已通过 `raw_sources.load_pharmgkb_bulk_facts()` 与 `pgx/by-substance` overlay 面向 PWA / Pages UI 暴露；线上生产快照需下一次部署后更新。

### 缺少 / 待补

> **2026-05-21 状态**：`pgx/by-substance` endpoint 已新增，合并 `pgx_relationship`、`pgx_clinical_annotation`、`pgx_drug_label`、`pgx_guideline` 四种 fact type。以下为剩余缺口。

| 缺口 | 影响 | 建议 |
|---|---|---|
| ~~缺少 `pgx/by-substance` endpoint~~ | ✅ 已新增 `pgx/by-substance` overlay | PWA 与 Pages UI 已接入 evidence-only 展示 |
| 缺少 gene / variant 维度索引 | 用户有基因型时无法反查药物 | 增加 `pgx/by-gene`、`pgx/by-variant`（未来增强） |
| PGx 与 CYP/enzyme 未融合 | 代谢解释断层 | 连接 PharmGKB PGx 与 openFDA/DailyMed enzyme_relation |
| UI 风险文案缺失 | 易被误解为个体化用药建议 | 明确“不构成处方建议；无基因型时仅提示潜在相关性” |

优先级：**高**。这是“个人多维动态代谢安全”区别于普通 DDI app 的关键层。

---

## 3.6 FooDrugs

原始位置：

```text
D:\metabolic-safety-data\raw\foodrugs
```

结构化输出：

```text
D:\metabolic-safety-data\structured_parallel_all\_source_parts\foodrugs\structured_facts.sqlite
D:\metabolic-safety-data\structured_parallel_all\jsonl\foodrugs.jsonl
```

### 已提取到结构化大库

| fact_type | 数量 | 已提取内容 |
|---|---:|---|
| food_interaction | 1,108,327 | food-drug 候选相互作用信号 |

示例语义：

```text
Grapefruit / abemaciclib
confidence: Low
source_tier: Signal
risk_level: Unknown
```

### 已进入当前 App Seed / Static API

旧快照中没有看到 FooDrugs 进入：

- App Seed source summary
- `public/api/manifest.json`
- 独立 `food-interactions` endpoint

当前分支已通过 `food-interactions/by-substance` overlay 暴露给 PWA / Pages UI；仍按 Low confidence / Signal / Unknown 次级展示。

### 缺少 / 待补

> **2026-05-21 状态**：`food-interactions/by-substance` endpoint 已新增。FooDrugs facts 按 drug 和 food/bioactive 双 subject 暴露，manifest records 按唯一 `fact_id` 去重。以下为剩余缺口。

| 缺口 | 影响 | 建议 |
|---|---|---|
| ~~缺少 `food-interactions/by-substance` endpoint~~ | ✅ 已新增 `food-interactions/by-substance` overlay | PWA / Pages UI 已接入次级 signal 展示与 disclaimer |
| 缺少食物实体归一 | grapefruit、grapefruit juice、pomelo 等难合并 | 建立 food ontology / alias table |
| 缺少高可信交叉验证 | 候选信号可能有大量噪声 | 与 openFDA/DailyMed 标签和 DDInter 交叉标记 |
| UI 风险边界缺失 | 用户可能把信号当禁忌 | 明确 Low confidence / Signal / Unknown |

优先级：**中**。只作为 DFI 补盲，不作为强规则。

---

## 3.7 OnSIDES

原始位置：

```text
D:\metabolic-safety-data\raw\onsides\onsides-v3.1.1.zip
```

结构化输出：

```text
D:\metabolic-safety-data\structured_parallel_all\_source_parts\onsides\structured_facts.sqlite
D:\metabolic-safety-data\structured_parallel_all\jsonl\onsides.jsonl
```

### 已提取到结构化大库

| fact_type | 数量 | 已提取内容 |
|---|---:|---|
| adverse_event | 1,209,425 | drug/product - adverse event 候选信号 |

示例语义：

```text
adverse event: Allergic reaction / Anaphylaxis / Bradycardia
confidence: Low
source_tier: Signal
risk_level: Unknown
```

### 已进入当前 App Seed / Static API

旧快照中没有看到 OnSIDES 进入：

- App Seed source summary
- 顶层 Static API manifest
- 独立 `adverse-events` / `adverse-signals` endpoint

PWA 代码中存在 adverse signal / openFDA FAERS live fallback 接入点；当前分支已新增静态 OnSIDES `adverse-signals/by-substance` endpoint 与 PWA / Pages UI evidence-only 展示。

### 缺少 / 待补

> **2026-05-21 状态**：`adverse-signals/by-substance` endpoint 已新增。每行包含 `signal_policy: "label_derived_signal_not_incidence_or_causality"`。以下为剩余缺口。

| 缺口 | 影响 | 建议 |
|---|---|---|
| ~~缺少 `adverse-signals/by-substance` endpoint~~ | ✅ 已新增 `adverse-signals/by-substance` overlay | PWA / Pages UI 已接入次级 signal 展示与 disclaimer |
| 缺少与标签 warning 的分层 | 信号可能和监管 warning 混淆 | UI 分为 Label Warning vs Signal |
| 缺少因果/频率边界说明 | 用户可能误读为“必然发生” | 文案说明“不代表因果、不代表发生率” |
| 缺少去重和 MedDRA 分组 | adverse event 展示可能过多 | 需要 top signals、分类、去重、分页 |

优先级：**中**。适合警戒补盲，不适合作为核心风险判定。

---

## 4. 跨库缺口矩阵

| 能力 | 当前结构化库 | 当前 App Seed | 本地 Static API 2026-05-18 | 远端 Static API 2026-05-20 | 主要缺口 |
|---|---:|---:|---:|---:|---|
| DDI pairwise interaction | DDInter 外部导入，不在 `structured_parallel_all` summary | 160,235 | 160,235 | 160,235 | 机制/标签解释不足 |
| substance identity | 471,025 bulk facts | 2,286 seed substances / 2,405 identity facts | 119,875 substances | 204,657 substances | canonical merge 与来源分解不足 |
| dose candidates | 554,958 | 未作为 seed 全量 | 554,958 | 727,971 | 噪声过滤、route/population 标准化；本地需追平远端 |
| dose rules | 可由 631,530+ source facts 生成 | 34 | 44,891 | 46,723 | App Seed / Static API 口径不一致 |
| overdose warning | 76,572 | 少量 seed | 76,572 | 74,198 | 远端可能过滤/去重策略不同；需解释差异 |
| label sections | 1,014,845 | 522 `source_text` | `label-sections/by-substance` overlay ✅ | `label-sections/by-substance` overlay ✅ | overlay 已补齐；PWA / Pages UI 已接入 evidence-only 展示 |
| safety warnings | 276,656 | 很少 | `safety-warnings/by-substance` overlay ✅ | `safety-warnings/by-substance` overlay ✅ | overlay 已补齐；需 UI 层与监管 warning 分层 |
| drug effects / indication / mechanism | 277,352 | 少量 ChEMBL/openFDA seed | `drug-effects/by-substance` overlay ✅ | 162,368 | overlay 已补齐；还缺 source breakdown UI |
| pharmacokinetics | 44,621；本地 ChEMBL 分源为 0 | 58 | `pharmacokinetics/by-substance` overlay ✅ | 52,670 | overlay 已补齐；本地结构化快照需重跑 ChEMBL activities |
| enzyme / CYP relation | 78,120 | 2 | `enzyme-relations/by-substance` overlay ✅ | 111,328 | overlay 已补齐；仍需 CYP/PGx/interaction 解释融合 |
| interaction signals | 67,102 | 未进入 | `interaction-signals/by-substance` overlay ✅ | — | overlay 已补齐；review-required label signal，不替代 DDInter |
| PGx | 41,750+ PGx facts | 未进入 | `pgx/by-substance` overlay ✅ | `pgx/by-substance` overlay ✅ | overlay 已补齐（合并 4 种 fact type）；CI raw_sources PGx 抽取仍需正式迁移 |
| food-drug signal | 1,108,327 | 未进入 | `food-interactions/by-substance` overlay ✅ | `food-interactions/by-substance` overlay ✅ | overlay 已补齐；FooDrugs 为低可信 signal，PWA / Pages UI 已加边界说明 |
| adverse event signal | 1,209,425 | 未进入 | `adverse-signals/by-substance` overlay ✅ | `adverse-signals/by-substance` overlay ✅ | overlay 已补齐；OnSIDES 为 signal，PWA / Pages UI 已分层展示 |
| chemical properties | ChEMBL identity 中有部分 | 145 ChEMBL seed facts | 未见独立 endpoint | 未见独立 endpoint | 缺 MW/ALogP/SMILES 等结构化展示 |

---

## 5. 安全边界与展示规则

必须保持以下原则：

```text
Unknown 不等于 safe。
Low confidence 不应覆盖 High / Medium confidence。
Signal 不应降级 Regulatory / Guideline / CuratedDB 的风险。
自动抽取候选不等于临床建议。
```

推荐按来源层级展示：

| source_tier | 代表来源 | 推荐用途 |
|---|---|---|
| Regulatory | openFDA, DailyMed, FDA guidance | 标签证据、剂量候选、warning、PK/CYP 原文 |
| Guideline | PharmGKB guideline, CPIC/DPWG, EFSA/CDC 等 | 指南/PGx/安全阈值证据 |
| CuratedDB | DDInter, ChEMBL | DDI 主库、化学/机制数据库 |
| Literature | PubMed / peer-reviewed facts | 补充证据，需上下文 |
| Community | PsychonautWiki 等 | 低可信候选，不做强规则 |
| Signal | FooDrugs, OnSIDES, FAERS-like signals | 补盲提示，不代表因果/发生率 |

---

## 6. 推荐补齐路线

### P0：统一构建口径

1. 解释并修复 `build/manifest.json` 与 `public/api/manifest.json` 的 `dose_rules` 差异：
   - App Seed: `dose_rules_count = 34`
   - Static API: `dose_rules = 44,891`
2. 在 README 或 manifest 中明确：
   - App Seed 是离线精简库；或
   - App Seed 应包含 Static API 的高优先级 dose rules。

### P0：本地追平远端 2026-05-20 Static API

本地 `public/api` 当前落后远端 GitHub Pages API。短期需要确认本地是否应重跑与远端相同的 CI overlay 链路：

```text
python tools/export_dose_overlay.py \
  --api-dir public/api \
  --max-content-per-substance 24 \
  --fact-json .cache/metabolic-source-facts/openfda_label/evidence_facts.json \
  --fact-json .cache/metabolic-source-facts/dailymed/evidence_facts.json \
  --fact-json .cache/metabolic-source-facts/chembl/evidence_facts.json \
  --fact-json .cache/metabolic-source-facts/foodrugs/evidence_facts.json \
  --fact-json .cache/metabolic-source-facts/onsides/evidence_facts.json \
  --fact-json .cache/metabolic-source-facts/pharmgkb/evidence_facts.json
```

或使用本地结构化 SQLite / JSONL 等价输入导出：

```text
python tools/export_dose_overlay.py \
  --api-dir public/api \
  --max-content-per-substance 24 \
  --structured-db D:/metabolic-safety-data/structured_parallel_all/structured_facts.sqlite
```

追平目标：

- 顶层 `manifest.json` 登记 `drug_effect_overlay`、`enzyme_relation_overlay`、`pharmacokinetics_overlay`。
- 生成 `drug-effects/manifest.json`。
- 生成 `enzyme-relations/manifest.json` 与 `enzyme-relations/by-substance/...`。
- 生成 `pharmacokinetics/manifest.json` 与 `pharmacokinetics/by-substance/...`。
- 更新 `paths.drug_effects_by_substance`、`paths.enzyme_relations_by_substance`、`paths.pharmacokinetics_by_substance`。
- 重建 `search/manifest.json` 和 search shards。

注意：如果使用本地 `structured_parallel_all`，ChEMBL 分源目前没有 `pharmacokinetics`；如需远端 `chembl_activities` 8,918 PK facts，需要重跑当前 `raw_sources.load_chembl_bulk_facts()` 路径或同步远端 source layer。

### P1：把监管标签事实暴露为 evidence drawer ✅ 已完成 endpoint 层

已通过 `tools/export_dose_overlay.py` 统一导出：

```text
label-sections/by-substance/{id}.json     ✅
safety-warnings/by-substance/{id}.json    ✅
pharmacokinetics/by-substance/{id}.json   ✅
enzyme-relations/by-substance/{id}.json   ✅
interaction-signals/by-substance/{id}.json ✅
```

目的：让 openFDA / DailyMed 的监管证据可追溯，而不是只输出 dose overlays。

UI 状态：PWA `SubstanceDetailView` 与 Pages `site/app.js` 已读取并展示这些 overlay 路径，并附带 evidence-only / review-required 提示。后续可继续增强默认折叠、分页和来源分组。

### P1：接入 PharmGKB PGx ✅ 已完成 endpoint 层

已通过 overlay 导出新增：

```text
pgx/by-substance/{id}.json  ✅  （合并 pgx_relationship + pgx_clinical_annotation + pgx_drug_label + pgx_guideline）
pgx/by-gene/{gene}.json      未实现（按基因维度反查，未来增强）
pgx/by-variant/{variant}.json 未实现（按变异维度反查，未来增强）
```

UI 文案必须强调：不构成个体化处方建议。

当前实现状态：

- `tools/analyze_raw_mirror.py` 的本地结构化分析脚本已能从 PharmGKB 生成：
  - `pgx_relationship`
  - `pgx_clinical_annotation`
  - `pgx_drug_label`
  - `pgx_guideline`
- CI 远端 source layer 使用的 `src/metabolic_safety_etl/raw_sources.py::load_pharmgkb_bulk_facts()` 已补齐上述 PGx fact types，并有 `tests/test_raw_sources.py` 覆盖。

因此 PGx endpoint 已完成“正式 ETL 抽取 + overlay 导出 + PWA/Pages UI 展示”闭环；剩余增强是 `pgx/by-gene`、`pgx/by-variant` 等反查索引，以及 CYP/PGx/interaction 的解释融合。

### P2：ChEMBL half-life / 化学属性增强

新增 ChEMBL activity 抽取：

```text
ChEMBL activities where standard_type in T1/2 / half-life patterns
  -> EvidenceFact(fact_type="pharmacokinetics")
```

保留：

- value
- unit
- assay description
- species/context
- document reference
- confidence

### P2：低可信信号层 ✅ 已完成 endpoint 层

已新增：

```text
food-interactions/by-substance/{id}.json  ✅
adverse-signals/by-substance/{id}.json    ✅
```

要求（已内置于 overlay policy）：

- 默认折叠或次级展示。
- 明确 `confidence: Low`、`source_tier: Signal`、`risk_level: Unknown`。
- 不参与强告警降级。

UI 状态：PWA 与 Pages UI 已次级展示信号层并附带非因果/非发生率/低置信度 disclaimer。剩余工作：默认折叠、分页、Top signals 分组与食物实体归一（grapefruit ontology）。

### P2：剂量候选质量控制

当前 dose candidate 中可能存在非剂量阈值，例如：

```text
Creatinine Clearance greater than or equal to 50 mL/minute
```

这类内容不应作为“药物剂量”直接参与 overdose/dose limit 判断。

建议将 dose parser 输出拆为：

| 类型 | 示例 | 是否可生成 dose_rule |
|---|---|---|
| dose_amount | 500 mg | 可以，需 route/population |
| daily_max | maximum 4000 mg/day | 可以，较高优先级 |
| single_max | not exceed 1000 mg per dose | 可以，需审核 |
| frequency | every 6 hours | 不能单独作为 dose ceiling |
| renal_threshold | CrCl 50 mL/min | 不能作为 dose ceiling |
| lab_threshold | ALT/AST, INR 等 | 不能作为 dose ceiling |
| PK_value | half-life 12 h | 进入 PK，不进入 dose ceiling |

---

## 7. 建议验证用小试用集

推荐用以下物质验证全链路：

```text
ibuprofen
warfarin
simvastatin
ethanol
clobazam
quetiapine
sertraline
alprazolam
```

验证目标：

| 物质 | 验证能力 |
|---|---|
| ibuprofen | 标签 warning、剂量、DDI、overdose |
| warfarin | DDI、食物、PGx、出血风险 |
| simvastatin | CYP3A4、grapefruit、SLCO1B1 |
| grapefruit | FooDrugs / 标签 DFI 信号 |
| ethanol | DDInter、CNS depressant、摄入阈值 |
| clobazam | CYP2C19 / PGx / CNS 风险 |
| quetiapine | CYP3A4、镇静、代谢风险 |
| sertraline | 标签剂量、CYP、DDI、DailyMed seed |
| alprazolam | CYP3A4、grapefruit、CNS depressant |

---

## 8. 后续开发 checklist

- [ ] 明确 App Seed 与 Static API 的职责边界。
- [ ] 修复或解释 `dose_rules_count: 34` vs `dose_rules: 44,891`。
- [x] 本地追平远端 `2026-05-20` API：补 `drug-effects` manifest registration、`enzyme-relations`、`pharmacokinetics` overlay。→ 2026-05-21 已通过 overlay 导出补齐所有 overlay。
- [ ] 明确本地 `structured_parallel_all` 与远端 source-layer cache 的差异，尤其 ChEMBL activities PK。
- [ ] 给 Static API 增加 bulk source breakdown manifest，区分 App Seed sources 与 structured bulk sources。
- [x] 增加 label section / safety warning / PK / enzyme endpoint。→ 2026-05-21 已新增 `label-sections`、`safety-warnings`、`interaction-signals`、`pharmacokinetics`、`enzyme-relations` overlay。
- [x] 增加 PharmGKB PGx endpoint。→ 2026-05-21 已新增 `pgx/by-substance` overlay（合并 4 种 fact type）。
- [x] 将 `tools/analyze_raw_mirror.py` 中 PharmGKB PGx 抽取逻辑迁移到正式 ETL `raw_sources.py` 并补测试。→ 2026-05-21 已完成 `load_pharmgkb_bulk_facts()` PGx 抽取与测试覆盖。
- [x] 增加 FooDrugs / OnSIDES signal endpoint，并默认低可信展示。→ 2026-05-21 已新增 `food-interactions`、`adverse-signals` overlay。
- [ ] 重跑或同步 ChEMBL half-life activity 抽取，使本地结构化快照含 `chembl_activities` PK facts。
- [ ] 增强 substance canonical merge：RxNorm、openFDA active ingredient、DailyMed SPL、ChEMBL、PharmGKB。
- [ ] 对 dose candidate 加类型分类和噪声过滤。
- [ ] 在 PWA 中为每条 evidence 进一步完善 review_status、原文/来源链接展示（已展示 source_tier / confidence / risk_level 的主要字段）。
- [x] PWA UI 接入新增 overlay（label-sections、safety-warnings、interaction-signals、food-interactions、adverse-signals、pgx）evidence drawer / 信号层组件。→ 2026-05-21 已接入 `SubstanceDetailView`，Pages UI 也已展示新增 overlay。
- [ ] PGx 按基因/变异维度反查 endpoint（`pgx/by-gene`、`pgx/by-variant`）。

---

## 9. 当前最重要的差距一句话

~~当前系统已经把大量原始数据库转成了 `EvidenceFact`，但真正进入 App Seed / PWA 可见层的仍以 DDInter 和 dose overlay 为主；下一步应把 openFDA / DailyMed 的监管证据、PharmGKB 的 PGx、ChEMBL 的 PK/机制、FooDrugs/OnSIDES 的低可信信号按来源层级安全地暴露出来，并统一离线 seed 与在线 static API 的构建口径。~~

**2026-05-21 更新**：所有六大来源（openFDA、DailyMed、ChEMBL、FooDrugs、OnSIDES、PharmGKB）的 evidence overlay 已通过 `tools/export_dose_overlay.py` 统一导出为静态 API endpoint，顶层 manifest 已登记全部 overlay counts/paths/keys；PWA 与 Pages UI 已接入新增 overlay，并保留 evidence-only / review-required / signal-not-causality / PGx-not-prescribing 安全边界。下一步重点是：(1) App Seed 与 Static API 口径对齐；(2) 剂量候选噪声过滤和类型分类；(3) ChEMBL activity PK 与本地结构化快照同步；(4) overlay UI 默认折叠、分页、Top signals 分组。
