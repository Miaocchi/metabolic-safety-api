import { clippedText, formatHours, formatNumber, riskSortValue, routeLabel } from "../lib/format";
import { observedBaselineHalfLifeHours, substanceDetailForModel } from "../lib/pk";
import type { SubstanceBundle } from "../types";
import { DetailSection } from "./DetailSection";
import { EvidenceCard } from "./EvidenceCard";
import { OverlayNotice } from "./OverlayNotice";
import { RiskBadge } from "./RiskBadge";

export function SubstanceDetailView({ bundle }: { bundle: SubstanceBundle }) {
  const detail = substanceDetailForModel(bundle) || bundle.detail;
  const observedHalfLife = observedBaselineHalfLifeHours(detail);
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
          <strong>{formatHours(detail.base_half_life || observedHalfLife)}</strong>
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
      {bundle.labelSections.length > 0 && (
        <DetailSection title="标签文段">
          <OverlayNotice tone="soft" body="标签文段为证据摘录，不是临床用药指导。" />
          {bundle.labelSections.slice(0, 6).map((row, index) => (
            <EvidenceCard key={`${row.fact_id || index}`} row={row as unknown as Record<string, unknown>} textField="text" />
          ))}
        </DetailSection>
      )}
      {bundle.safetyWarnings.length > 0 && (
        <DetailSection title="安全警告">
          <OverlayNotice tone="warning" body="安全警告为机器提取标签文段，不能替代更高层级的人工审核规则。" />
          {bundle.safetyWarnings.slice(0, 6).map((row, index) => (
            <article className="evidence-card" key={`${row.fact_id || index}`}>
              <strong>{row.section || "warning"}</strong>
              <span>{[row.source_name, row.source_tier, row.confidence].filter(Boolean).join(" · ")}</span>
              {row.risk_level && <RiskBadge level={row.risk_level} />}
              <p>{clippedText(row.warning_text, 220)}</p>
            </article>
          ))}
        </DetailSection>
      )}
      {bundle.interactionSignals.length > 0 && (
        <DetailSection title="交互信号">
          <OverlayNotice tone="warning" body="交互信号来源于标签摘录，需人工复核，不能替代 DDInter 风险规则。" />
          {bundle.interactionSignals.slice(0, 6).map((row, index) => (
            <article className="evidence-card" key={`${row.fact_id || index}`}>
              <strong>{row.section || "interaction"}</strong>
              <span>{[row.source_name, row.source_tier, row.confidence].filter(Boolean).join(" · ")}</span>
              {row.risk_level && <RiskBadge level={row.risk_level} />}
              <p>{clippedText(row.interaction_text, 220)}</p>
            </article>
          ))}
        </DetailSection>
      )}
      {bundle.foodInteractions.length > 0 && (
        <DetailSection title="食物交互候选">
          <OverlayNotice tone="warning" body="FooDrugs 食物/生物活性物候选信号为低置信度文本挖掘，不代表因果关系，不能替代监管或人工审核证据。" />
          {bundle.foodInteractions.slice(0, 6).map((row, index) => (
            <article className="evidence-card" key={`${row.fact_id || index}`}>
              <strong>{[row.drug, row.food_or_bioactive].filter(Boolean).join(" + ") || "食物交互"}</strong>
              <span>{[row.source_name, row.source_tier, row.confidence].filter(Boolean).join(" · ")}</span>
              {row.risk_level && <RiskBadge level={row.risk_level} />}
              <p>{clippedText(row.mechanism || row.note, 220)}</p>
            </article>
          ))}
        </DetailSection>
      )}
      {bundle.adverseSignals.length > 0 && (
        <DetailSection title="不良事件信号">
          <OverlayNotice tone="warning" body="OnSIDES 不良信号来源于标签文本挖掘，不代表发生率或因果关系，仅作低置信度复核参考。" />
          {bundle.adverseSignals.slice(0, 6).map((row, index) => (
            <article className="evidence-card" key={`${row.fact_id || index}`}>
              <strong>{row.event || "不良事件"}</strong>
              <span>{[row.source_name, row.source_tier, row.confidence].filter(Boolean).join(" · ")}</span>
              {row.risk_level && <RiskBadge level={row.risk_level} />}
              <p>{clippedText(row.label_section || row.match_method, 220)}</p>
            </article>
          ))}
        </DetailSection>
      )}
      {bundle.pgx.length > 0 && (
        <DetailSection title="PGx 基因-药物证据">
          <OverlayNotice tone="danger" body="PGx 行为 PharmGKB/ClinPGx 证据展示，不是个体化处方建议。Unknown ≠ 安全。" />
          {bundle.pgx.slice(0, 6).map((row, index) => (
            <article className="evidence-card" key={`${row.fact_id || index}`}>
              <strong>{[row.gene || (Array.isArray(row.genes) ? row.genes.join(", ") : ""), row.section || row.fact_type || "pgx"].filter(Boolean).join(" · ")}</strong>
              <span>{[row.source_name, row.source_tier, row.confidence].filter(Boolean).join(" · ")}</span>
              {row.level_of_evidence && <span className="pgx-level">证据等级: {row.level_of_evidence}</span>}
              <p>{clippedText(row.summary || row.evidence || row.association, 220)}</p>
            </article>
          ))}
        </DetailSection>
      )}
    </div>
  );
}
