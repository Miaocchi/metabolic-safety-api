import { clippedText, displayName, formatHours, formatNumber, riskClass, riskLabel, riskSortValue, routeLabel } from "../lib/format";
import type { SubstanceBundle } from "../types";
import { DetailSection } from "./DetailSection";
import { EvidenceCard } from "./EvidenceCard";
import { RiskBadge } from "./RiskBadge";

export function SubstanceDetailView({ bundle }: { bundle: SubstanceBundle }) {
  const detail = bundle.detail;
  const topInteractions = [...bundle.interactions].sort((a, b) => riskSortValue(b.risk_level) - riskSortValue(a.risk_level)).slice(0, 30);
  return (
    <div className="detail-view">
      <div className="kv-grid">
        <div>
          <span>类别</span>
          <strong>{detail.category || "Unknown"}</strong>
        </div>
        <div>
          <span>半衰期</span>
          <strong>{formatHours(detail.base_half_life)}</strong>
        </div>
        <div>
          <span>相互作用</span>
          <strong>{formatNumber(detail.interaction_count || bundle.interactions.length)}</strong>
        </div>
        <div>
          <span>剂量规则</span>
          <strong>{formatNumber(detail.dose_rule_count || bundle.doseRules.length)}</strong>
        </div>
      </div>
      <DetailSection title="药效 / PK">
        {[...bundle.drugEffects.slice(0, 5), ...bundle.pharmacokinetics.slice(0, 5)].map((row, index) => (
          <EvidenceCard key={`${row.fact_id || index}`} row={row} />
        ))}
      </DetailSection>
      <DetailSection title="剂量规则">
        {bundle.doseRules.slice(0, 8).map((rule) => (
          <article className="evidence-card" key={rule.rule_id}>
            <strong>{rule.rule_id || "dose_rule"}</strong>
            <span>
              {routeLabel(rule.route)} · {rule.window_hours || "?"}h · {rule.unit || "mg"}
            </span>
            <p>{rule.thresholds?.map((threshold) => threshold.label || `${threshold.limit} ${rule.unit}`).join(" / ") || rule.note}</p>
          </article>
        ))}
      </DetailSection>
      <DetailSection title="相互作用 Top">
        {topInteractions.map((row) => (
          <article className="evidence-card interaction" key={row.interaction_id}>
            <strong>{[row.substance_a_name || row.substance_a_name_en, row.substance_b_name || row.substance_b_name_en].filter(Boolean).join(" / ")}</strong>
            <RiskBadge level={row.risk_level} />
            <p>{clippedText(row.note || row.mechanism || row.action, 180)}</p>
          </article>
        ))}
      </DetailSection>
      <DetailSection title="过量警告">
        {bundle.overdoseWarnings.slice(0, 6).map((row, index) => (
          <EvidenceCard key={`${row.fact_id || index}`} row={row} />
        ))}
      </DetailSection>
    </div>
  );
}
