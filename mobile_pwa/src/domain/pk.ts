/**
 * @module domain/pk
 *
 * Pure pharmacokinetic model helpers — dose conversion, one-compartment
 * absorption/elimination curves, PMI calculation, and exposure grouping.
 * No side effects, no IndexedDB, no network.
 *
 * Canonical source — `lib/pk.ts` re-exports this module for backward compat.
 */
import type { JournalEntry, PharmacokineticRow, SubstanceBundle, SubstanceDetail, UserProfile } from "../types";

export const defaultProfile: UserProfile = {
  weightKg: 70,
  heightCm: 170,
  ageYears: 35,
  bodyFatPct: 20,
  sleepDebtHours: 0,
  coreTempC: 37,
  metabolicType: "EM",
};

const routeProfiles = {
  Oral: { ka: 1.0, f: 1.0, instant: false },
  Sublingual: { ka: 1.8, f: 0.85, instant: true },
  Insufflated: { ka: 2.2, f: 0.75, instant: true },
  Topical: { ka: 0.25, f: 0.35, instant: false },
  IV: { ka: 999, f: 1.0, instant: true },
  Other: { ka: 1.0, f: 1.0, instant: false },
};

const stomachProfiles = {
  Fasting: { ka: 1.5, f: 1.0 },
  Light: { ka: 1.0, f: 1.0 },
  Heavy: { ka: 0.5, f: 1.08 },
};

const metabolicProfiles = {
  UM: { ke: 1.45 },
  EM: { ke: 1.0 },
  IM: { ke: 0.72 },
  PM: { ke: 0.45 },
};

const DEFAULT_HALF_LIFE_HOURS = 4;
const DEFAULT_DURATION_MINUTES = 360;

export interface CurvePoint {
  x: number;
  y: number;
}

export interface CurveSeries {
  id: string;
  label: string;
  unit: string;
  color: string;
  points: CurvePoint[];
  current: number;
  baseHalfLifeHours: number;
  adjustedHalfLifeHours: number;
}

export interface CurveModel {
  series: CurveSeries[];
  total: CurvePoint[];
  maxY: number;
  start: number;
  end: number;
}

export function doseInMg(entry: JournalEntry) {
  const dose = Number(entry.dosage || 0);
  if (!Number.isFinite(dose) || dose <= 0) return 0;
  const unit = String(entry.unit || "mg").toLowerCase();
  if (unit === "mg") return dose;
  if (unit === "g") return dose * 1000;
  if (unit === "ug" || unit === "mcg") return dose / 1000;
  return dose;
}

function positiveNumber(value: unknown) {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? numeric : undefined;
}

function normalizePkRows(rows: unknown): PharmacokineticRow[] {
  if (!Array.isArray(rows)) return [];
  return rows.filter((row): row is PharmacokineticRow => Boolean(row && typeof row === "object"));
}

function mergePkRows(...groups: PharmacokineticRow[][]) {
  const merged: PharmacokineticRow[] = [];
  const seen = new Set<string>();
  for (const row of groups.flat()) {
    const key = [
      row.fact_id,
      row.source_name,
      row.standard_type,
      row.route,
      row.half_life_hours,
      row.half_life_hours_mean,
      row.half_life_hours_upper,
      row.onset_minutes,
      row.duration_minutes,
    ].map((part) => String(part ?? "")).join("|");
    if (seen.has(key)) continue;
    seen.add(key);
    merged.push(row);
  }
  return merged;
}

function pharmacokineticRowsForSubstance(substance?: SubstanceDetail | null) {
  if (!substance) return [];
  return mergePkRows(
    normalizePkRows(substance.pharmacokinetics),
    normalizePkRows(substance.pharmacokinetics_detail),
    normalizePkRows(substance.remote_evidence?.pharmacokinetics),
  );
}

function firstPkNumber(rows: PharmacokineticRow[], fields: Array<keyof PharmacokineticRow>) {
  for (const row of rows) {
    for (const field of fields) {
      const value = positiveNumber(row[field]);
      if (value !== undefined) return value;
    }
  }
  return undefined;
}

export function substanceDetailForModel(bundle?: SubstanceBundle) {
  if (!bundle?.detail) return undefined;
  const detailRows = pharmacokineticRowsForSubstance(bundle.detail);
  const bundleRows = normalizePkRows(bundle.pharmacokinetics);
  const rows = mergePkRows(detailRows, bundleRows);
  if (!rows.length) return bundle.detail;
  return {
    ...bundle.detail,
    pharmacokinetics: rows,
    remote_evidence: {
      ...(bundle.detail.remote_evidence || {}),
      pharmacokinetics: rows,
    },
  } satisfies SubstanceDetail;
}

export function observedBaselineHalfLifeHours(substance?: SubstanceDetail | null) {
  return positiveNumber(substance?.base_half_life)
    ?? firstPkNumber(pharmacokineticRowsForSubstance(substance), ["half_life_hours", "half_life_hours_mean", "half_life_hours_upper"]);
}

export function baselineHalfLifeHours(substance?: SubstanceDetail | null) {
  return observedBaselineHalfLifeHours(substance) ?? DEFAULT_HALF_LIFE_HOURS;
}

export function baselineDurationMinutes(substance?: SubstanceDetail | null) {
  return positiveNumber(substance?.base_duration)
    ?? firstPkNumber(pharmacokineticRowsForSubstance(substance), ["duration_minutes"])
    ?? DEFAULT_DURATION_MINUTES;
}

export function adjustedPkParams(entry: JournalEntry, substance?: SubstanceDetail, profile: UserProfile = defaultProfile) {
  const route = routeProfiles[entry.route] || routeProfiles.Other;
  const stomach = stomachProfiles[entry.stomachState] || stomachProfiles.Light;
  const baseHalfLifeHours = baselineHalfLifeHours(substance);
  const bodyFactor = Math.max(0.65, Math.min(1.55, profile.weightKg / 70));
  const tempFactor = Math.pow(2, (Math.min(profile.coreTempC, 40.5) - 37) / 10);
  const sleepFactor = Math.max(0.72, 1 - profile.sleepDebtHours * 0.0125);
  const phenotype = metabolicProfiles[profile.metabolicType] || metabolicProfiles.EM;
  const adjustedHalfLifeHours = Math.max(0.25, baseHalfLifeHours / Math.max(0.25, phenotype.ke * tempFactor * sleepFactor));
  const kePerHour = Math.log(2) / adjustedHalfLifeHours;
  const kaPerHour = route.instant ? 0 : Math.max(0.05, route.ka * stomach.ka);
  const vdLiters = Math.max(1, profile.weightKg * (0.55 + profile.bodyFatPct / 200) * bodyFactor);
  return {
    modelType: route.instant ? "instant_elimination" : "one_compartment_absorption",
    baseHalfLifeHours,
    adjustedHalfLifeHours,
    kePerHour,
    kaPerHour,
    bioavailabilityFactor: route.f * stomach.f,
    vdLiters,
  };
}

export function concentrationAt(tHours: number, dose: number, params: ReturnType<typeof adjustedPkParams>) {
  if (tHours < 0) return 0;
  const amount = Math.max(Number(dose || 0), 0) * params.bioavailabilityFactor;
  const vd = Math.max(params.vdLiters, 1);
  const ke = Math.max(params.kePerHour, 0.001);
  if (params.modelType === "instant_elimination" || !params.kaPerHour) return (amount / vd) * Math.exp(-ke * tHours);
  let ka = Math.max(params.kaPerHour, 0.001);
  if (Math.abs(ka - ke) < 0.001) ka += 0.001;
  const value = (amount * ka) / (vd * (ka - ke)) * (Math.exp(-ke * tHours) - Math.exp(-ka * tHours));
  return Math.max(value, 0);
}

export function activeEntries(entries: JournalEntry[], bundles: Record<string, SubstanceBundle>, profile: UserProfile, now = Date.now()) {
  return entries.filter((entry) => {
    const substance = substanceDetailForModel(bundles[entry.substanceId]);
    const params = adjustedPkParams(entry, substance, profile);
    const windowMinutes = Math.max(params.adjustedHalfLifeHours * 6 * 60, baselineDurationMinutes(substance), 60);
    return (now - entry.timestamp) / 60000 <= windowMinutes && entry.timestamp <= now + 5 * 60000 && entryHasMeaningfulExposure(entry, bundles, profile, now, 24);
  });
}

export function calculatePMI(profile: UserProfile = defaultProfile) {
  const phenotypeFactor = (metabolicProfiles[profile.metabolicType] || metabolicProfiles.EM).ke;
  const tempFactor = 1 + (Math.min(profile.coreTempC, 40.5) - 37) * 0.07;
  const sleepFactor = Math.max(0.72, 1 - profile.sleepDebtHours * 0.015);
  const bmi = profile.weightKg / Math.pow(profile.heightCm / 100, 2);
  const bmiFactor = Math.max(0.8, Math.min(1.2, 1 - (bmi - 22) * 0.005));
  const ageFactor = Math.max(0.75, Math.min(1.15, 1 - (profile.ageYears - 30) * 0.004));

  const pmi = 100 * phenotypeFactor * tempFactor * sleepFactor * bmiFactor * ageFactor;
  return {
    value: Math.round(Math.max(20, Math.min(180, pmi))),
    raw: pmi,
    phenotypeFactor,
    tempFactor,
    sleepFactor,
    bmiFactor,
    ageFactor,
    bmi,
  };
}

export function pmiLabel(value: number) {
  if (value >= 140) return { label: "极快代谢", color: "#007aff" };
  if (value >= 110) return { label: "偏快代谢", color: "#5ac8fa" };
  if (value >= 90) return { label: "正常代谢", color: "#34c759" };
  if (value >= 70) return { label: "偏慢代谢", color: "#ff9500" };
  if (value >= 50) return { label: "慢代谢", color: "#ff3b30" };
  return { label: "极慢代谢", color: "#af52de" };
}

function minutesBetween(fromTimestamp: number, toTimestamp: number) {
  return (toTimestamp - fromTimestamp) / 60000;
}

function fmt(n: number, digits = 3) {
  if (!Number.isFinite(n)) return "0";
  if (digits === 0) return Math.round(n).toString();
  return n.toFixed(digits);
}

function fmtDuration(minutes: number) {
  if (minutes < 1) return "<1分钟";
  if (minutes < 60) return `${Math.round(minutes)}分钟`;
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return m > 0 ? `${h}小时${m}分钟` : `${h}小时`;
}

export function exposureMetricsForEntry(entry: JournalEntry, params: ReturnType<typeof adjustedPkParams>, horizonHours = 24) {
  const dose = Number(entry.dosage || 0);
  const samples = 144;
  let auc = 0;
  let previous = concentrationAt(0, dose, params);
  let cmax = previous;
  let tmax = 0;
  for (let i = 1; i <= samples; i += 1) {
    const t = horizonHours * (i / samples);
    const value = concentrationAt(t, dose, params);
    auc += ((previous + value) / 2) * (horizonHours / samples);
    if (value > cmax) {
      cmax = value;
      tmax = t;
    }
    previous = value;
  }
  return { auc24: auc, cmax, tmaxHours: tmax };
}

export function forwardExposureMetricsForEntry(entry: JournalEntry, params: ReturnType<typeof adjustedPkParams>, now = Date.now(), horizonHours = 24) {
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
    horizonHours,
    unit: concentrationUnitLabel(entry),
  };
}

function concentrationUnitLabel(entry: JournalEntry) {
  const unit = String(entry.unit || "mg").toLowerCase();
  if (unit === "mcg") return "ug";
  return unit || "mg";
}

function exposureIsMeaningful(metrics?: { current?: number; peak?: number; auc24?: number; horizonHours?: number; cmax?: number } | null, referenceCmax = 0, floor = 0.0005, relativeFloor = 0.01) {
  if (!metrics) return false;
  const horizonHours = Math.max(1, Number(metrics.horizonHours || 24));
  const averageForward = Number(metrics.auc24 || 0) / horizonHours;
  const level = Math.max(Number(metrics.current || 0), Number(metrics.peak || 0), averageForward);
  const reference = Number(referenceCmax || metrics.cmax || 0);
  const threshold = Math.max(floor, Number.isFinite(reference) && reference > 0 ? reference * relativeFloor : 0);
  return level > threshold;
}

function exposureReferenceCmax(entry: JournalEntry, params: ReturnType<typeof adjustedPkParams>, horizonHours = 24) {
  const metrics = exposureMetricsForEntry(entry, params, Math.max(24, horizonHours));
  return Number(metrics.cmax || 0);
}

export function entryHasMeaningfulExposure(entry: JournalEntry, bundles: Record<string, SubstanceBundle>, profile: UserProfile, now = Date.now(), horizonHours = 24) {
  const substance = substanceDetailForModel(bundles[entry.substanceId]);
  const params = adjustedPkParams(entry, substance, profile);
  const metrics = forwardExposureMetricsForEntry(entry, params, now, horizonHours);
  if (!metrics) return false;
  return exposureIsMeaningful(metrics, exposureReferenceCmax(entry, params, horizonHours));
}

export function meaningfulExposureEntries(entries: JournalEntry[], bundles: Record<string, SubstanceBundle>, profile: UserProfile, now = Date.now(), horizonHours = 24) {
  return entries.filter((entry) => entryHasMeaningfulExposure(entry, bundles, profile, now, horizonHours));
}
export function forwardExposureIndex(auc24: number, peak: number, minutesToPeak: number, halfLifeHours: number) {
  const aucScore = Math.min(62, Math.log10(Math.max(auc24, 0) + 1) * 30);
  const peakScore = Math.min(26, Math.log10(Math.max(peak, 0) + 1) * 16);
  const peakSoonScore = minutesToPeak > 0 && minutesToPeak <= 180 ? 8 : 0;
  const lingerScore = Math.min(12, Math.max(0, Number(halfLifeHours || 0) - 6) * 0.8);
  return Math.round(Math.min(100, Math.max(0, aucScore + peakScore + peakSoonScore + lingerScore)));
}

export interface ForwardExposureGroup {
  id: string;
  name: string;
  auc24: number;
  current: number;
  peak: number;
  minutesToPeak: number;
  halfLifeHours: number;
  count: number;
  unit: string;
  index: number;
}

export function forwardExposureGroups(entries: JournalEntry[], bundles: Record<string, SubstanceBundle>, profile: UserProfile, now = Date.now(), horizonHours = 24): ForwardExposureGroup[] {
  const bySubstance = new Map<string, { id: string; name: string; auc24: number; current: number; peak: number; minutesToPeak: number | null; halfLifeHours: number; count: number; unitSet: Set<string> }>();
  entries.forEach((entry) => {
    const substance = substanceDetailForModel(bundles[entry.substanceId]);
    const params = adjustedPkParams(entry, substance, profile);
    const metrics = forwardExposureMetricsForEntry(entry, params, now, horizonHours);
    if (!metrics || !exposureIsMeaningful(metrics, exposureReferenceCmax(entry, params, horizonHours))) return;
    const key = pmiSubstanceKey(entry, substance);
    const group = bySubstance.get(key) || {
      id: key,
      name: entry.substanceName,
      auc24: 0,
      current: 0,
      peak: 0,
      minutesToPeak: null,
      halfLifeHours: 0,
      count: 0,
      unitSet: new Set<string>(),
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
    bySubstance.set(key, group);
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

export interface PmiResult {
  pmi: number;
  level: string;
  levelClass: string;
  riskScore: number;
  exposureScore: number;
  modifierScore: number;
  forwardScore: number;
  complexityScore: number;
  forwardIndex: number;
  totalExposure: number;
  activeCount: number;
  substanceCount: number;
  rows: Array<{ id: string; name: string; exposure: number; cmax: number; halfLife: number; halfLifeRatio: number; sleepDebtHours: number; coreTempC: number; count?: number }>;
  forwardRows: ForwardExposureGroup[];
}

function normalizePmiSubstanceKey(value = "") {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[\s_\-./()[\]{}]+/g, "")
    .replace(/[·•]/g, "");
}

function pmiSubstanceKey(entry: JournalEntry, substance?: SubstanceBundle["detail"]) {
  const display = substance?.name_zh || substance?.name_en || entry.substanceName || entry.substanceSnapshot?.name_zh || entry.substanceSnapshot?.name_en;
  return normalizePmiSubstanceKey(display || "") || String(entry.substanceId || substance?.id || "").toLowerCase();
}
function pmiRiskScore(risks: Array<{ level: string; id?: string; type?: string; subject?: string; note?: string }>) {
  const riskRank: Record<string, number> = {
    Contraindicated: 6, Dangerous: 6, Unsafe: 5, Major: 5, Moderate: 4,
    Synergy: 3, Minor: 2, "Low Risk": 1, NoKnownClinicalSignificance: 0, Unknown: 1,
  };
  const deduped = new Map<string, number>();
  for (const risk of risks) {
    const score = Math.max(0, riskRank[risk.level] ?? 1);
    if (!score) continue;
    const key = [risk.id, risk.type, risk.subject, risk.level, risk.note?.slice(0, 80)].filter(Boolean).join("|");
    if (!deduped.has(key) || score > (deduped.get(key) || 0)) deduped.set(key, score);
  }
  const scores = [...deduped.values()].sort((a, b) => b - a);
  const weighted = scores.reduce((sum, score, index) => sum + score * Math.pow(0.58, index), 0);
  const severeBonus = scores.some((score) => score >= 5) ? 5 : scores.some((score) => score >= 4) ? 2 : 0;
  return Math.min(34, weighted * 4.2 + severeBonus);
}

function pmiGroupedRows(rows: Array<{ id: string; name: string; exposure: number; cmax: number; halfLife: number; halfLifeRatio: number; sleepDebtHours: number; coreTempC: number }>) {
  const bySubstance = new Map<string, { id: string; name: string; exposure: number; cmax: number; halfLife: number; halfLifeRatio: number; sleepDebtHours: number; coreTempC: number; count: number }>();
  for (const row of rows) {
    const group = bySubstance.get(row.id) || { ...row, exposure: 0, cmax: 0, halfLife: row.halfLife || 0, count: 0 };
    group.exposure += Math.max(0, row.exposure || 0);
    group.cmax = Math.max(group.cmax, row.cmax || 0);
    group.halfLife = Math.max(group.halfLife || 0, row.halfLife || 0);
    group.halfLifeRatio = Math.max(group.halfLifeRatio || 1, row.halfLifeRatio || 1);
    group.count += 1;
    bySubstance.set(row.id, group);
  }
  return [...bySubstance.values()].sort((a, b) => b.exposure - a.exposure);
}
function pmiExposureScore(rows: Array<{ id: string; exposure: number; cmax: number }>) {
  const bySubstance = new Map<string, { current: number; peak: number; count: number }>();
  for (const row of rows) {
    const group = bySubstance.get(row.id) || { current: 0, peak: 0, count: 0 };
    group.current += Math.max(0, row.exposure || 0);
    group.peak = Math.max(group.peak, row.cmax || 0);
    group.count += 1;
    bySubstance.set(row.id, group);
  }
  const groups = [...bySubstance.values()];
  const totalCurrent = groups.reduce((sum, group) => sum + group.current, 0);
  const strongestCurrent = groups.reduce((max, group) => Math.max(max, group.current), 0);
  const strongestPeak = groups.reduce((max, group) => Math.max(max, group.peak), 0);
  const stackPenalty = Math.max(0, groups.length - 1) * 1.2 + Math.max(0, rows.length - groups.length) * 0.45;
  const score = Math.log10(totalCurrent + 1) * 8
    + Math.log10(strongestCurrent + 1) * 5
    + Math.log10(strongestPeak + 1) * 3
    + stackPenalty;
  return Math.min(28, score);
}

function pmiModifierScore(rows: Array<{ halfLifeRatio: number; sleepDebtHours: number; coreTempC: number }>) {
  if (!rows.length) return 0;
  const maxSleepDebt = Math.max(...rows.map((row) => row.sleepDebtHours || 0));
  const maxTemp = Math.max(...rows.map((row) => row.coreTempC || 37));
  const maxHalfLifeRatio = Math.max(...rows.map((row) => row.halfLifeRatio || 1));
  const sleepScore = Math.min(7, maxSleepDebt * 0.45);
  const tempScore = maxTemp >= 39 ? 5 : maxTemp >= 37.8 ? 3 : 0;
  const halfLifeScore = Math.min(8, Math.max(0, maxHalfLifeRatio - 1) * 5);
  return Math.min(18, sleepScore + tempScore + halfLifeScore);
}

function pmiComplexityScore(rows: Array<{ id: string }>) {
  const substanceCount = new Set(rows.map((row) => row.id).filter(Boolean)).size;
  const entryCount = rows.length;
  return Math.min(10, Math.max(0, substanceCount - 1) * 1.7 + Math.max(0, entryCount - substanceCount) * 0.25);
}

function pmiForwardScore(forwardRows: ForwardExposureGroup[]) {
  if (!forwardRows.length) return 0;
  const sorted = [...forwardRows].sort((a, b) => b.index - a.index);
  const top = sorted[0]?.index || 0;
  const blended = sorted.reduce((sum, row, index) => sum + row.index * Math.pow(0.5, index), 0);
  return Math.min(18, top * 0.09 + blended * 0.05);
}

export function calculateFullPMI(
  entries: JournalEntry[],
  bundles: Record<string, SubstanceBundle>,
  profile: UserProfile,
  risks: Array<{ level: string; id?: string; type?: string; subject?: string; note?: string }>,
  now = Date.now(),
): PmiResult {
  if (!entries.length) {
    return {
      pmi: 0, level: "等待模型计算", levelClass: "empty",
      riskScore: 0, exposureScore: 0, modifierScore: 0, forwardScore: 0, complexityScore: 0, forwardIndex: 0,
      totalExposure: 0, activeCount: 0, substanceCount: 0, rows: [], forwardRows: [],
    };
  }
  const meaningfulEntries = meaningfulExposureEntries(entries, bundles, profile, now, 24);
  if (!meaningfulEntries.length) {
    return {
      pmi: 0, level: "低负荷", levelClass: "low",
      riskScore: 0, exposureScore: 0, modifierScore: 0, forwardScore: 0, complexityScore: 0, forwardIndex: 0,
      totalExposure: 0, activeCount: 0, substanceCount: 0, rows: [], forwardRows: [],
    };
  }
  const rows = meaningfulEntries.map((entry) => {
    const substance = substanceDetailForModel(bundles[entry.substanceId]);
    const params = adjustedPkParams(entry, substance, profile);
    const elapsedHours = minutesBetween(entry.timestamp, now) / 60;
    const exposure = elapsedHours < 0 ? 0 : concentrationAt(elapsedHours, Number(entry.dosage || 0), params);
    const metrics = exposureMetricsForEntry(entry, params);
    const halfLifeRatio = params.adjustedHalfLifeHours / Math.max(params.baseHalfLifeHours || 1, 1);
    return {
      id: pmiSubstanceKey(entry, substance),
      name: entry.substanceName,
      exposure,
      cmax: metrics.cmax,
      halfLife: params.adjustedHalfLifeHours,
      halfLifeRatio,
      sleepDebtHours: profile.sleepDebtHours || 0,
      coreTempC: profile.coreTempC || 37,
    };
  }).sort((a, b) => b.exposure - a.exposure);
  const groupedRows = pmiGroupedRows(rows);
  const totalExposure = groupedRows.reduce((sum, row) => sum + row.exposure, 0);
  const riskScore = pmiRiskScore(risks);
  const exposureScore = pmiExposureScore(rows);
  const modifierScore = pmiModifierScore(rows);
  const complexityScore = pmiComplexityScore(rows);
  const forwardRows = forwardExposureGroups(meaningfulEntries, bundles, profile, now, 24);
  const forwardIndex = forwardRows.length ? Math.min(100, Math.round(forwardRows.reduce((sum, row) => sum + row.index, 0) / Math.sqrt(forwardRows.length))) : 0;
  const forwardScore = pmiForwardScore(forwardRows);
  const substanceCount = groupedRows.length;
  const pmi = Math.max(0, Math.min(100, Math.round(10 + riskScore + exposureScore + modifierScore + complexityScore + forwardScore)));
  const level = pmi >= 80 ? "高负荷" : pmi >= 55 ? "中负荷" : "低负荷";
  const levelClass = pmi >= 80 ? "high" : pmi >= 55 ? "medium" : "low";
  return {
    pmi, level, levelClass, riskScore, exposureScore, modifierScore, forwardScore, complexityScore, forwardIndex,
    totalExposure, activeCount: meaningfulEntries.length, substanceCount, rows: groupedRows, forwardRows,
  };
}

export function buildCurveModel(entries: JournalEntry[], bundles: Record<string, SubstanceBundle>, profile: UserProfile, zoom = 1, offsetHours = 0, now = Date.now()) {
  const active = activeEntries(entries, bundles, profile, now);
  const earliest = active.length ? Math.min(...active.map((entry) => entry.timestamp)) : now - 60 * 60000;
  const horizonHours = Math.max(3, 12 / Math.max(0.25, zoom));
  const start = Math.min(earliest, now - 2 * 60 * 60000) + offsetHours * 60 * 60000;
  const end = now + horizonHours * 60 * 60000 + offsetHours * 60 * 60000;
  const samples = 140;
  const palette = ["#007aff", "#34c759", "#ff9500", "#af52de", "#ff2d55", "#5ac8fa"];
  const total = Array.from({ length: samples + 1 }, (_, i) => ({ x: i / samples, y: 0 }));
  const series = active.map((entry, index) => {
    const params = adjustedPkParams(entry, substanceDetailForModel(bundles[entry.substanceId]), profile);
    const dose = doseInMg(entry);
    const points = total.map((point, i) => {
      const timestamp = start + (end - start) * (i / samples);
      const tHours = (timestamp - entry.timestamp) / 3600000;
      const y = concentrationAt(tHours, dose, params);
      return { x: point.x, y };
    });
    points.forEach((point, i) => {
      total[i].y += point.y;
    });
    const currentHours = (now - entry.timestamp) / 3600000;
    return {
      id: entry.id,
      label: entry.substanceName,
      unit: "mg/L",
      color: palette[index % palette.length],
      points,
      current: concentrationAt(currentHours, dose, params),
      baseHalfLifeHours: params.baseHalfLifeHours,
      adjustedHalfLifeHours: params.adjustedHalfLifeHours,
    };
  });
  const maxY = Math.max(1, ...series.flatMap((row) => row.points.map((point) => point.y)), ...total.map((point) => point.y));
  return { series, total, maxY, start, end };
}
