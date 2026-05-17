# 个人多维动态代谢与安全管理系统：本地 ETL 原型

这个目录是先在电脑上运行和验证的数据层原型。目标不是直接给出临床用药建议，而是把 PK、PD、DDI、DFI、药物基因组、药物警戒和社区补盲数据统一成可追溯的证据事实，再导出移动端可灌入的种子库。

## 当前实现内容

- 本地证据事实模型：每条事实都带来源层级、可信度、安全等级、证据文本、抽取方式和审核状态。
- 融合规则：社区数据和低可信度数据不能把更高风险来源降级；`Unknown` 不等于安全。
- 导出物：`init_substances.json`、`init_interactions.json`、`evidence_facts.json`、`app_seed.sqlite`。
- 可选在线适配器：openFDA label 文本抓取、PsychonautWiki GraphQL 候选数据抓取。
- 离线测试：不依赖第三方包，不需要数据库服务。

## 快速运行

```powershell
$env:PYTHONPATH="src"
python -m metabolic_safety_etl.cli demo --out build
python -m unittest discover -s tests
```

生成文件：

```text
build/init_substances.json
build/init_interactions.json
build/evidence_facts.json
build/manifest.json
build/app_seed.sqlite
```

## 拉取监管标签原文作为证据源

```powershell
$env:PYTHONPATH="src"
python -m metabolic_safety_etl.cli fetch-openfda --term ibuprofen --limit 3 --out data/openfda_ibuprofen_facts.json
python -m metabolic_safety_etl.cli inspect --input data/openfda_ibuprofen_facts.json
```

openFDA 适配器只把标签段落保存成 `source_text` 事实，不会自动把自然语言转成安全规则。后续应由规则解析、LLM 候选抽取和人工复核生成 `drug_interaction`、`food_interaction` 或 `pharmacokinetics` 事实。

## 拉取社区候选数据

```powershell
$env:PYTHONPATH="src"
python -m metabolic_safety_etl.cli fetch-psychonautwiki --limit 10 --out data/psychonautwiki_facts.json
```

PsychonautWiki 输出被标记为 `source_tier=Community` 和 `use_policy=candidate_signal`，只能补盲，不能覆盖监管标签、指南或已审核策展库。

## 移动端接入边界

移动端首版只读取 `init_substances.json` 和 `init_interactions.json` 作为只读核心库；`evidence_facts.json` 用于详情页溯源和调试。历史日志必须保存当时的参数快照，不能只引用当前核心库，否则上游库更新会改变历史解释。

## 安全边界

这是本地数据工程原型，不是医疗器械级 CDSS。任何进入用户提醒的规则都需要来源复核、版本签名、回归测试和明确的免责声明。`NoKnownClinicalSignificance` 表示未发现明确临床意义相互作用；`Unknown` 表示资料不足，不能显示为安全。

## 桌面测试端

已经提供一个无第三方依赖的本地桌面 Web 测试端，用于在电脑上验证移动端之前的数据和交互逻辑。

启动：

```powershell
$env:PYTHONPATH="src"
python -m metabolic_safety_etl.cli demo --out build
python desktop_app/server.py
```

打开：

```text
http://127.0.0.1:8765
```

功能：

- 读取 `build/init_substances.json` 和 `build/init_interactions.json`。
- 在浏览器 localStorage 中保存本地摄入日志。
- 新增日志后检查活跃时间窗内的两两 DDI/DFI。
- 用 Canvas 绘制简化的一室吸收/消除估算曲线。
- 曲线横轴从最早活跃摄入时间展开到未来 12 小时，并用竖线标出当前时间；新增记录可手动选择摄入时间。
- 支持按单条删除日志；刷新页面后会重新同步 Canvas 尺寸并恢复曲线。
- 支持乙醇按饮酒体积和酒精度换算为纯乙醇克数后入账。
- 风险详情显示来源层级、可信度、机制、冲突状态。

停止后台服务时可执行：

```powershell
Stop-Process -Id (Get-Content build/desktop_server.pid)
```

## 导入真实 DDInter 数据

当前 `build` 已经不是 4 条演示 fixture，而是从 DDInter 2.0 Download 页面下载并导入的数据：

```text
substances_core: 1939
interactions_core: 160235
evidence_facts: 162174
```

当前构建额外补入了 Tandospirone 和茶多酚/EGCG 候选事实，因此本地桌面库为：

```text
substances_core: 1941
interactions_core: 160235
evidence_facts: 162180
```

如果在桌面端设置页拉取公开源候选事实并重建，数量会随 `data/optional/public_facts.json` 增加。当前本机已试拉 RxNav `ibuprofen`，重建后为 `substances_core: 1992`、`interactions_core: 160235`、`evidence_facts: 162287`。

重新生成：

```powershell
$env:PYTHONPATH="src"
python -m metabolic_safety_etl.cli import-ddinter --input-dir data/raw/ddinter --out build
```

桌面端 `/api/seed` 为了避免浏览器一次加载 100MB 以上证据全文，会从 `build/app_seed.sqlite` 读取精简后的 substance 和 interaction 数据；完整证据仍保存在：

```text
build/evidence_facts.json
build/app_seed.sqlite
```

## 多源接入状态

查看源状态：

```powershell
$env:PYTHONPATH="src"
python -m metabolic_safety_etl.cli sources --out build/source_status.json
```

已接入并可运行：

- `DDInter 2.0`：本地 CSV 主交互库。
- `openFDA Drug Label`：监管标签段落 API，输出 `source_text`。
- `DailyMed SPL`：SPL 元数据 API，完整 XML 段落抽取待扩展。
- `RxNav / RxNorm`：RxCUI 和实体归一化 API，不再提供 DDI。
- `ChEMBL`：分子实体和物化性质 API。
- `PsychonautWiki`：社区 ROA/剂量/持续时间候选数据。
- `Local supplemental facts`：用于 DDInter 未覆盖物质，如 Tandospirone。

桌面端“数据源设置”面板已经暴露这些非商业公开源的可选更新入口。openFDA、DailyMed、RxNav、ChEMBL 需要输入关键词；PsychonautWiki 可直接拉取一批社区候选。更新会先写入 `data/optional/public_facts.json`，点击“重建本地库”后才合入 `build/app_seed.sqlite` 和移动端种子 JSON。

需要本地下载后再导入的信号源：`FooDrugs`、`OnSIDES`、`PharmGKB/ClinPGx`。需要商业授权的源：`DrugBank`、`FDB`、`Medi-Span`、`Certara DIDB`。

一次性抓取公开 API 示例：

```powershell
$env:PYTHONPATH="src"
python -m metabolic_safety_etl.cli fetch-public --term warfarin --limit 2 --out build/public_warfarin_facts.json
```

## PopPK 桌面模型

桌面端曲线现在使用单室一阶吸收模型：

```text
C(t) = F * D * ka / (Vd * (ka - ke)) * (e^(-ke*t) - e^(-ka*t))
```

当给药途径为 `静脉/瞬时` 时自动降级为消除模型：

```text
C(t) = F * D / Vd * e^(-ke*t)
```

乙醇走单独的饮酒换算和 Widmark 趋势模型：`纯乙醇 g = 酒量 ml × 酒精度 %vol × 0.789`，分布容积按体脂修正后的总身体水估算，消除按近似零级消除趋势绘制。

当前参与修正的维度：体重、身高、体脂率、代谢表型、给药途径、胃部状态、脂溶性标签。该模型仍是个人日志和趋势估算模型，不是临床给药建议。


## GitHub Pages Remote Static API

The project can export the fused drug database as a GitHub Pages compatible static JSON API. This lets the desktop/mobile client keep a smaller local database and query a user-configured remote source only when local search misses.

Generate locally:

```powershell
$env:PYTHONPATH='src'
python -m metabolic_safety_etl.cli export-static-api --input-dir build --out public/api
```

Automated publishing is defined in `.github/workflows/build-data-api.yml`. After enabling GitHub Pages with the GitHub Actions source, the workflow builds `public/api` and deploys it. In the local app settings, configure the remote source at the `/api` level, for example `https://<user>.github.io/<repo>/api`. See `docs/REMOTE_STATIC_API.md`.


### GitHub Pages 多源融合构建

当前 GitHub Pages 工作流不再只导出本地 DDInter；它会运行 `build-public-api`，把以下可直接使用的非商业源合并为远程静态 API：

- 本地 DDInter 2.0 CSV、中文别名、补充事实、剂量规则。
- 已缓存的 `data/optional/*.json` 候选事实。
- RxNav / RxNorm、ChEMBL、DailyMed SPL、openFDA Drug Label 的公开 API enrichment。
- PsychonautWiki GraphQL 的 ROA/剂量/持续时间候选数据。

本地小规模验证：

```powershell
$env:PYTHONPATH='src'
python -m metabolic_safety_etl.cli build-public-api --out build --api-out public/api --max-public-terms 20 --public-limit 1 --psychonautwiki-pages 1
```

FooDrugs、OnSIDES、PharmGKB/ClinPGx 这类大包源先下载到工作站并转换为 EvidenceFact JSON 后，放入 `data/optional` 即可被同一构建命令融合。商业授权源不会自动接入。

## Cloudflare Pages Remote Static API

Cloudflare Pages is also supported for the same static JSON API. Use `.github/workflows/build-data-api-cloudflare-pages.yml`, set GitHub secrets `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN`, and optionally set repository variable `CLOUDFLARE_PAGES_PROJECT`. The client remote URL should be `https://<project>.pages.dev/api`. See `docs/CLOUDFLARE_PAGES_API.md`.
