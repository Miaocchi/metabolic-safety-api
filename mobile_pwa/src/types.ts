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
  label_sections?: string;
  safety_warnings?: string;
  interaction_signals?: string;
  food_interactions?: string;
  adverse_signals?: string;
  pgx?: string;
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

export interface PharmacokineticRow extends EvidenceTextRow {
  half_life_hours?: number | string | null;
  half_life_hours_mean?: number | string | null;
  half_life_hours_upper?: number | string | null;
  onset_minutes?: number | string | null;
  duration_minutes?: number | string | null;
  route?: string | null;
  standard_type?: string | null;
}

export interface SubstanceRemoteEvidence {
  drug_effects?: EvidenceTextRow[];
  pharmacokinetics?: PharmacokineticRow[];
  enzyme_relations?: EvidenceTextRow[];
  [key: string]: unknown;
}

// ── Content overlay row types ──────────────────────────────────────────

/** DailyMed/openFDA label section excerpt — evidence text, not clinical instructions. */
export interface LabelSectionRow {
  fact_id?: string;
  source_key?: string;
  source_name?: string;
  source_url?: string;
  source_tier?: string;
  confidence?: string;
  section?: string;
  text?: string;
}

/** Label-derived safety warning excerpt — machine extraction, must not override curated rules. */
export interface SafetyWarningRow {
  fact_id?: string;
  source_key?: string;
  source_name?: string;
  source_url?: string;
  source_tier?: string;
  confidence?: string;
  risk_level?: RiskLevel;
  section?: string;
  warning_text?: string;
}

/** Label interaction excerpt — review-required signal, does not replace DDInter risk rules. */
export interface InteractionSignalRow {
  fact_id?: string;
  source_key?: string;
  source_name?: string;
  source_url?: string;
  source_tier?: string;
  confidence?: string;
  risk_level?: RiskLevel;
  section?: string;
  interaction_text?: string;
  signal_policy?: string;
}

/**
 * FooDrugs text-mined food/bioactive-drug candidate signal.
 *
 * SAFETY: Low-confidence, non-causal. Must NOT downgrade regulatory or curated evidence.
 */
export interface FoodInteractionRow {
  fact_id?: string;
  source_key?: string;
  source_name?: string;
  source_url?: string;
  source_tier?: string;
  confidence?: string;
  risk_level?: RiskLevel;
  drug?: string;
  drug_id?: string;
  food_or_bioactive?: string;
  food_or_bioactive_id?: string;
  mechanism?: string;
  note?: string;
  signal_policy?: string;
}

/**
 * OnSIDES label-derived adverse event signal.
 *
 * SAFETY: Not incidence rates or causal attribution — low-confidence review cues only.
 */
export interface AdverseSignalRow {
  fact_id?: string;
  source_key?: string;
  source_name?: string;
  source_url?: string;
  source_tier?: string;
  confidence?: string;
  risk_level?: RiskLevel;
  event?: string;
  meddra_id?: string;
  label_section?: string;
  match_method?: string;
  score?: number | string | null;
  signal_policy?: string;
}

/**
 * PharmGKB/ClinPGx gene-drug evidence row.
 *
 * SAFETY: Evidence-only. Not individualized prescribing recommendations.
 */
export interface PgxRow {
  fact_id?: string;
  fact_type?: string;
  source_key?: string;
  source_name?: string;
  source_url?: string;
  source_tier?: string;
  confidence?: string;
  section?: string;
  gene?: string;
  genes?: string[];
  variants?: string | string[] | null;
  phenotypes?: string | string[] | null;
  level_of_evidence?: string;
  testing_level?: string;
  has_prescribing_info?: boolean;
  has_dosing_info?: boolean;
  association?: string;
  related_entity?: string;
  related_entity_type?: string;
  guideline_id?: string;
  name?: string;
  summary?: string;
  evidence?: string;
  policy?: string;
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
  label_section_count?: number;
  safety_warning_count?: number;
  interaction_signal_count?: number;
  food_interaction_count?: number;
  adverse_signal_count?: number;
  pgx_count?: number;
  source_summary?: SourceSummary[];
  pharmacokinetics?: PharmacokineticRow[];
  pharmacokinetics_detail?: PharmacokineticRow[];
  remote_evidence?: SubstanceRemoteEvidence;
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

export interface SubstanceBundle {
  detail: SubstanceDetail;
  interactions: InteractionRow[];
  doseRules: DoseRule[];
  doseCandidates: EvidenceTextRow[];
  overdoseWarnings: EvidenceTextRow[];
  drugEffects: EvidenceTextRow[];
  pharmacokinetics: PharmacokineticRow[];
  enzymeRelations: EvidenceTextRow[];
  labelSections: LabelSectionRow[];
  safetyWarnings: SafetyWarningRow[];
  interactionSignals: InteractionSignalRow[];
  foodInteractions: FoodInteractionRow[];
  adverseSignals: AdverseSignalRow[];
  pgx: PgxRow[];
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
