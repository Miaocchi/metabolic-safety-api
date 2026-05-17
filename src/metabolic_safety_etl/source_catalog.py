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
    SourceStatus("openfda_label", "openFDA Drug Label", "Regulatory", "connected_api", "fetch-openfda", "https://open.fda.gov/apis/drug/label/", "标签段落源，默认生成 source_text，需进一步抽取。"),
    SourceStatus("dailymed", "DailyMed SPL", "Regulatory", "connected_api", "fetch-dailymed", "https://dailymed.nlm.nih.gov/dailymed/app-support-web-services.cfm", "监管 SPL 元数据/API 接入；完整 XML 段落抽取待扩展。"),
    SourceStatus("rxnav", "RxNav / RxNorm", "Regulatory", "connected_api", "fetch-rxnav", "https://lhncbc.nlm.nih.gov/RxNav/APIs/RxNormAPIs.html", "实体归一化和 RxCUI 映射；不再提供 DDI。"),
    SourceStatus("chembl", "ChEMBL", "CuratedDB", "connected_api", "fetch-chembl", "https://www.ebi.ac.uk/chembl/", "化学实体与物化性质接入。"),
    SourceStatus("psychonautwiki", "PsychonautWiki", "Community", "connected_api", "fetch-psychonautwiki", "https://api.psychonautwiki.org", "社区 ROA/剂量/持续时间候选源。"),
    SourceStatus("supplemental", "Local supplemental facts", "Literature", "connected_local_json", "import-ddinter --supplement-facts", "data/overrides/supplemental_facts.json", "用于 DDInter 未覆盖物质，如 Tandospirone。"),
    SourceStatus("dose_rules", "Dose rule seed library", "Regulatory", "connected_local_json", "import-dose-rules", "data/overrides/dose_rules.json", "Dose ceilings/window rules from DailyMed/openFDA/FDA/CDC evidence; consumed as data, not hardcoded UI logic."),
    SourceStatus("foodrugs", "FooDrugs", "Signal", "local_file_adapter_pending", "manual_import_pending", "https://zenodo.org/records/8192515", "数据体量大，建议下载后本地 SQL/CSV 解析；不直接作为临床规则。"),
    SourceStatus("onsides", "OnSIDES", "Signal", "local_file_adapter_pending", "manual_import_pending", "https://github.com/tatonetti-lab/onsides", "标签 NLP 抽取副作用源；只进候选信号。"),
    SourceStatus("pharmgkb", "PharmGKB / ClinPGx", "Guideline", "download_adapter_pending", "manual_import_pending", "https://api.pharmgkb.org/", "PGx/CPIC 数据需按下载包接入。"),
    SourceStatus("drugbank", "DrugBank", "LicensedCommercial", "license_required", "contract_required", "https://go.drugbank.com/", "商业/产品集成需要授权，不能直接打包。"),
    SourceStatus("fdb", "FDB MedKnowledge", "LicensedCommercial", "license_required", "contract_required", "https://www.fdbhealth.com/", "企业授权源。"),
    SourceStatus("medispan", "Medi-Span", "LicensedCommercial", "license_required", "contract_required", "https://www.wolterskluwer.com/en/solutions/medi-span/medi-span/drug-data", "企业授权源。"),
    SourceStatus("didb", "Certara DIDB", "LicensedCommercial", "license_required", "contract_required", "https://www.certara.com/drug-interaction-database-didb/", "企业授权源。"),
]


def source_status_dicts() -> list[dict[str, str]]:
    return [asdict(source) for source in SOURCES]
