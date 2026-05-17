# 整体方案：电脑端先实现，验证后下放移动端

## 1. 目标

先在电脑端建立一个可重复运行的本地 ETL 与证据融合管线，把多源药物数据转换为移动端可离线灌入的种子库。移动端只承担记录、估算、提醒和溯源展示；复杂抓取、清洗、LLM 抽取和人工复核留在电脑端完成。

## 2. 数据分层

| 层级 | 数据源 | 用途 | 默认策略 |
| --- | --- | --- | --- |
| L1 监管标签层 | DailyMed SPL、openFDA labels、FDA CYP tables | 禁忌、警告、PK 段落、监管证据 | 可进入核心证据，但自然语言仍需抽取和审核 |
| L2 标准本体层 | RxNorm/RxNav、UNII、ATC、PubChem、ChEMBL ID | 实体归一化、药名/NDC/RxCUI 映射 | 只做映射，不直接判断安全 |
| L3 策展知识层 | DDInter、PharmGKB/ClinPGx、ChEMBL、DrugBank(授权后) | DDI/DFI、PK/PD、PGx、靶点通路 | 进入核心候选库，按证据等级融合 |
| L4 信号发现层 | FAERS/openFDA event、OnSIDES、TwoSIDES、FooDrugs、文献挖掘 | 发现长尾风险和新信号 | 只能作为候选信号，不能直接拦截 |
| L5 社区补盲层 | PsychonautWiki、TripSit 等 | 官方覆盖不足的物质/组合补盲 | 低可信度候选，不得覆盖高等级来源 |

## 3. 中间事实模型

所有来源先转换为 `EvidenceFact`，避免把来源格式直接写死进 App：

```json
{
  "fact_type": "pharmacokinetics | enzyme_relation | drug_interaction | food_interaction | source_text",
  "subject_ids": ["ibuprofen", "warfarin"],
  "claim": {"mechanism": "..."},
  "risk_level": "Contraindicated | Major | Moderate | Minor | NoKnownClinicalSignificance | Unknown",
  "confidence": "High | Medium | Low | Unknown",
  "source_tier": "Regulatory | Label | Guideline | CuratedDB | Literature | Signal | Community",
  "source_name": "DailyMed",
  "source_url": "...",
  "evidence_quote": "...",
  "extraction_method": "api | parser | llm | manual",
  "review_status": "unreviewed | machine_checked | human_reviewed",
  "use_policy": "core_rule | evidence_source | candidate_signal | mapping_only"
}
```

## 4. 融合规则

1. `Unknown` 单独处理，不能映射为无风险。
2. 风险选择采用保守原则：同一组合存在多个已知风险时取最高风险。
3. 高可信来源不能被社区或信号源降级。
4. FAERS、TwoSIDES、FooDrugs、LLM 输出只生成候选事实，进入用户提醒前必须有审核状态。
5. 每条移动端规则必须保留 `evidence_refs`，详情页可追溯到来源。
6. 上游库更新时只替换官方核心表；用户自定义、历史日志和个人参数快照不被覆盖。

## 5. 电脑端运行流

```text
source adapters -> raw facts -> normalized EvidenceFact -> fusion -> mobile seed JSON + SQLite
```

当前原型已实现：

- `fetch-openfda`：抓取 openFDA 标签段落，生成监管来源事实。
- `fetch-psychonautwiki`：抓取社区 ROA/duration 候选事实。
- `build/demo`：融合事实并导出移动端种子库。
- `app_seed.sqlite`：用于桌面检查和未来 Room schema 对照。

## 6. 移动端落地方式

Android 首版建议：

- `Room`：导入 `substances_core`、`interactions_core`、`evidence_facts`。
- `SQLCipher`：加密用户日志库。
- `DataStore`：保存用户偏好和风险显示阈值。
- `Compose Canvas`：只绘制估算曲线，不显示“安全”结论。
- 历史日志写入时保存 `profile_snapshot` 和 `substance_param_snapshot`。

PWA 首版建议：

- `IndexedDB` 存储只读核心库与用户日志。
- `navigator.storage.persist()` 申请持久存储。
- PouchDB/CouchDB 只用于事件日志同步，不直接同步 SQLite 文件。

## 7. 后续扩展

- 增加 DailyMed SPL XML 批量解析器。
- 增加 RxNorm NDC/RxCUI 归一化缓存。
- 增加 DDInter CSV 导入器和风险等级映射。
- 增加 LLM 抽取队列，输出必须包含原文证据和 `review_status=unreviewed`。
- 增加移动端 Room Entity 和 migration 验证。
- 增加数据集签名，防止未审核库被手机端加载。
