from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class SourceStatus:
    key: str
    name: str
    tier: str
    status: str
    adapter: str
    url: str
    note: str


SOURCES = [
    SourceStatus("ddinter", "DDInter 2.0", "CuratedDB", "connected_local_csv", "import-ddinter", "https://ddinter2.scbdd.com/download/", "当前主交互库，已导入本地 CSV。"),
    SourceStatus("openfda_label", "openFDA Drug Label", "Regulatory", "connected_api_and_local_bulk", "fetch-openfda / raw_sources", "https://open.fda.gov/apis/drug/label/", "API 检索源 + data/raw/openfda_label 本地全量包抽取，可融合身份、PK 半衰期与 CYP 候选。"),
    SourceStatus("openfda_event", "openFDA FAERS adverse event", "Signal", "connected_api", "fetch-openfda-event", "https://open.fda.gov/apis/drug/event/", "FAERS 自发不良事件报告计数，只作为低可信度候选信号，不代表因果关系或确认联用冲突。"),
    SourceStatus("dailymed", "DailyMed SPL", "Regulatory", "connected_api_and_local_bulk", "fetch-dailymed / raw_sources", "https://dailymed.nlm.nih.gov/dailymed/app-support-web-services.cfm", "API 元数据 + data/raw/dailymed_spl 本地 SPL XML 抽取，可融合身份、PK 半衰期与 CYP 候选。"),
    SourceStatus("rxnav", "RxNav / RxNorm", "Regulatory", "connected_api", "fetch-rxnav", "https://lhncbc.nlm.nih.gov/RxNav/APIs/RxNormAPIs.html", "实体归一化和 RxCUI 映射；不再提供 DDI。"),
    SourceStatus("chembl", "ChEMBL", "CuratedDB", "connected_api_and_local_bulk", "fetch-chembl / raw_sources", "https://www.ebi.ac.uk/chembl/", "API 检索源 + 本地 SQLite/TAR 包抽取，可融合化学实体、物化性质与脂溶性候选。"),
    SourceStatus("psychonautwiki", "PsychonautWiki", "Community", "connected_api", "fetch-psychonautwiki", "https://api.psychonautwiki.org", "社区 ROA/剂量/持续时间候选源。"),
    SourceStatus("supplemental", "Local supplemental facts", "Literature", "connected_local_json", "import-ddinter --supplement-facts", "data/overrides/supplemental_facts.json", "用于 DDInter 未覆盖物质，如 Tandospirone。"),
    SourceStatus("dose_rules", "Dose rule seed library", "Regulatory", "connected_local_json", "import-dose-rules", "data/overrides/dose_rules.json", "Dose ceilings/window rules from DailyMed/openFDA/FDA/CDC evidence; consumed as data, not hardcoded UI logic."),
    SourceStatus("foodrugs", "FooDrugs", "Signal", "connected_local_bulk", "raw_sources", "https://zenodo.org/records/8192515", "下载到 data/raw/foodrugs 后可抽取药食冲突候选；只作为 Signal 层，不直接覆盖临床规则。"),
    SourceStatus("onsides", "OnSIDES", "Signal", "connected_local_bulk", "raw_sources", "https://github.com/tatonetti-lab/onsides", "下载到 data/raw/onsides 后可抽取长尾不良反应候选；只进 Signal 层。"),
    SourceStatus("pharmgkb", "PharmGKB / ClinPGx", "Guideline", "connected_local_bulk", "raw_sources", "https://api.pharmgkb.org/", "下载到 data/raw/pharmgkb 后可抽取 PGx/指南/药物实体，进入 Guideline 层。"),
    SourceStatus("drugbank", "DrugBank", "LicensedCommercial", "license_required", "contract_required", "https://go.drugbank.com/", "商业/产品集成需要授权，不能直接打包。"),
    SourceStatus("fdb", "FDB MedKnowledge", "LicensedCommercial", "license_required", "contract_required", "https://www.fdbhealth.com/", "企业授权源。"),
    SourceStatus("medispan", "Medi-Span", "LicensedCommercial", "license_required", "contract_required", "https://www.wolterskluwer.com/en/solutions/medi-span/medi-span/drug-data", "企业授权源。"),
    SourceStatus("didb", "Certara DIDB", "LicensedCommercial", "license_required", "contract_required", "https://www.certara.com/drug-interaction-database-didb/", "企业授权源。"),
]


def source_status_dicts() -> list[dict[str, str]]:
    return [asdict(source) for source in SOURCES]
