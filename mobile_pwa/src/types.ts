export type RiskLevel =
  | "Contraindicated"
  | "Dangerous"
  | "Unsafe"
  | "Major"
  | "Moderate"
  | "Synergy"
  | "Minor"
  | "Low Risk"
  | "NoKnownClinicalSignificance"
  | "Unknown"
  | string;

export type RouteKey = "Oral" | "Sublingual" | "Insufflated" | "Topical" | "IV" | "Other";
export type StomachState = "Fasting" | "Light" | "Heavy";

export interface ApiManifest {
  api_version?: string;
  dataset_version?: string;
  generated_at?: string;
  counts?: Record<string, number>;
  full_package?: {
    manifest?: string;
    zip?: string;
    zip_bytes?: number;
    zip_sha256?: string;
  };
  online_library?: {
    full_package?: ApiManifest["full_package"];
    source_library?: {
      facts_count?: number;
      index?: string;
      sources_count?: number;
    };
  };
  source_library?: {
    facts_count?: number;
    index?: string;
    sources_count?: number;
  };
  warning?: string;
  privacy_note?: string;
}

export interface SearchManifest {
  items?: number;
  policy?: string;
  shard_path?: string;
  shards?: Record<string, number>;
}

export interface ApiPaths {
  substance?: string;
  interactions?: string;
  dose_rules?: string;
  dose_candidates?: string;
  overdose_warnings?: string;
  drug_effects?: string;
  pharmacokinetics?: string;
  enzyme_relations?: string;
}

export interface SubstanceSummary {
  id: string;
  name_en?: string | null;
  name_zh?: string | null;
  aliases?: string[];
  category?: string | null;
  paths?: ApiPaths;
  remote_source?: string;
}

export interface SourceSummary {
  fact_id?: string;
  source_name?: string;
  source_tier?: string;
  source_url?: string;
  confidence?: string;
  review_status?: string;
  risk_level?: RiskLevel;
}

export interface SubstanceDetail extends SubstanceSummary {
  dataset_version?: string;
  base_half_life?: number | string | null;
  base_onset?: number | string | null;
  base_duration?: number | string | null;
  solubility?: string | null;
  identifiers?: Record<string, unknown>;
  cyp_tags?: string[];
  interaction_count?: number;
  dose_rule_count?: number;
  dose_candidate_count?: number;
  overdose_warning_count?: number;
  drug_effect_count?: number;
  pharmacokinetic_count?: number;
  enzyme_relation_count?: number;
  source_summary?: SourceSummary[];
  paths?: ApiPaths;
}

export interface InteractionRow {
  interaction_id?: string;
  substance_a_id?: string;
  substance_b_id?: string;
  substance_a_name?: string;
  substance_b_name?: string;
  substance_a_name_en?: string;
  substance_b_name_en?: string;
  interaction_type?: string;
  risk_level?: RiskLevel;
  confidence?: string;
  source_tier?: string;
  source_name?: string;
  source_url?: string;
  mechanism?: string | null;
  note?: string;
  action?: string;
  conflict_status?: string;
  remote_source?: string;
}

export interface DoseThreshold {
  kind?: "single" | "window" | string;
  label?: string;
  level?: RiskLevel;
  limit?: number;
}

export interface DoseRule {
  rule_id?: string;
  subject_id?: string;
  route?: string;
  unit?: string;
  window_hours?: number;
  thresholds?: DoseThreshold[];
  confidence?: string;
  source_name?: string;
  source_tier?: string;
  source_url?: string;
  note?: string;
  review_status?: string;
  population?: { review_required?: boolean; age_group?: string };
}

export interface EvidenceTextRow {
  fact_id?: string;
  section?: string;
  source_key?: string;
  source_name?: string;
  source_tier?: string;
  source_url?: string;
  confidence?: string;
  risk_level?: RiskLevel;
  text?: string;
  evidence?: string;
  note?: string;
  [key: string]: unknown;
}

export interface SubstanceBundle {
  detail: SubstanceDetail;
  interactions: InteractionRow[];
  doseRules: DoseRule[];
  doseCandidates: EvidenceTextRow[];
  overdoseWarnings: EvidenceTextRow[];
  drugEffects: EvidenceTextRow[];
  pharmacokinetics: EvidenceTextRow[];
  enzymeRelations: EvidenceTextRow[];
  fetchedAt: number;
}

export interface JournalEntry {
  id: string;
  substanceId: string;
  substanceName: string;
  timestamp: number;
  dosage: number;
  unit: "mg" | "ug" | "mcg" | "g" | "ml" | string;
  route: RouteKey;
  stomachState: StomachState;
  note?: string;
  substanceSnapshot?: SubstanceSummary;
}

export interface UserProfile {
  weightKg: number;
  heightCm: number;
  ageYears: number;
  bodyFatPct: number;
  sleepDebtHours: number;
  coreTempC: number;
  metabolicType: "UM" | "EM" | "IM" | "PM";
}

export interface RiskEvent {
  id: string;
  level: RiskLevel;
  title: string;
  subtitle?: string;
  note?: string;
  source?: string;
  sourceTier?: string;
  confidence?: string;
  entries?: JournalEntry[];
  kind?: string;
  reactions?: Array<{ reaction?: string; label?: string; count?: number }>;
}

export interface OfflineCacheRecord<T = unknown> {
  key: string;
  value: T;
  updatedAt: number;
  source?: string;
}

export interface PwaSettings {
  apiBase: string;
  localApiBase: string;
  cacheMode: "recent" | "none";
  localBackendEnabled: boolean;
  remoteProvider?: "github" | "cloudflare";
  staticDbMode?: "local-first" | "remote-first";
  /** When true, adverse-signal data falls back to live openFDA API calls. Default false (static/cache only). */
  liveSignalsEnabled?: boolean;
  /** When true, automatically sync authoritative static API shards on first launch / when cache is empty. Default true. */
  autoSyncOnLaunch?: boolean;
}

export interface StaticDbStats {
  manifests: number;
  searchShards: number;
  bundles: number;
  jsonFiles: number;
  lastSyncAt?: number;
  source?: string;
  datasetVersion?: string;
}

export interface LocalSeedPayload {
  manifest?: Record<string, unknown>;
  substances?: SubstanceSummary[];
  interactions?: InteractionRow[];
  dose_rules?: DoseRule[];
  /** camelCase alias — preferred by TS consumers; falls back to dose_rules. */
  doseRules?: DoseRule[];
}
