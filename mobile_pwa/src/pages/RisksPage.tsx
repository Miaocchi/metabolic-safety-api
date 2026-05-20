import { CheckCircle2, ChevronDown, RefreshCw } from "lucide-react";
import { EmptyState } from "../components/EmptyState";
import { Notice } from "../components/Notice";
import { riskClass, riskLabel, formatJournalEntry, riskSortValue } from "../lib/format";
import type { RiskEvent } from "../types";

function riskTypeLabel(risk: RiskEvent) {
  if (risk.kind === "conflict") return "冲突";
  if (risk.kind === "interaction") return "相互作用";
  if (risk.kind === "dose" || risk.kind === "overdose") return "过量";
  if (risk.kind === "signal") return "警戒信号";
  if (risk.kind === "model") return "模型提示";
  const text = `${risk.title} ${risk.subtitle || ""}`;
  if (/冲突|禁忌|contra/i.test(text)) return "冲突";
  if (/过量|剂量|overdose|dose/i.test(text)) return "过量";
  return "相互作用";
}

export function RisksPage({ risks, activeCount, onRefresh }: { risks: RiskEvent[]; activeCount: number; onRefresh: () => void }) {
  return (
    <div className="page-stack">
      <div className="risk-header">
        <div>
          <span>活跃摄入</span>
          <strong>{activeCount}</strong>
        </div>
        <div>
          <span>风险事件</span>
          <strong>{risks.length}</strong>
        </div>
        <div className="risk-header-action">
          <span>重新计算</span>
          <button type="button" onClick={onRefresh}>
            <RefreshCw size={17} />
          </button>
        </div>
      </div>
      <Notice
        tone="warning"
        title="安全边界"
        body="这是个人日志和趋势估算，不是临床决策支持。Unknown 表示资料不足，不能显示为安全。"
      />
      <div className="list">
        {risks.map((risk) => (
          <details key={risk.id} className={`risk-card ${riskClass(risk.level)}`}>
            <summary>
              <span>{riskLabel(risk.level)}</span>
              <div>
                <em className="risk-type-chip">{riskTypeLabel(risk)}</em>
                <strong>{risk.title}</strong>
                <small>{risk.subtitle || risk.source || "风险事件"}</small>
              </div>
              <ChevronDown size={18} />
            </summary>
            <div className="risk-card-body">
              <div className="risk-meta-grid">
                <span>级别 <b>{risk.level || "Unknown"}</b></span>
                <span>类型 <b>{riskTypeLabel(risk)}</b></span>
                <span>置信度 <b>{risk.confidence || "未记录"}</b></span>
                <span>来源层级 <b>{risk.sourceTier || "未记录"}</b></span>
              </div>
              <p>{risk.note || "暂无说明。"}</p>
              {risk.entries?.length ? (
                <div className="risk-entry-list">
                  {risk.entries.slice(0, 4).map((entry) => (
                    <span key={entry.id}>{entry.substanceName} · {formatJournalEntry(entry)}</span>
                  ))}
                </div>
              ) : null}
              {risk.kind === "signal" && risk.reactions?.length ? (
                <div className="risk-reaction-list">
                  {risk.reactions.slice(0, 5).map((reaction, index) => (
                    <span key={`${reaction.reaction || reaction.label || "reaction"}-${index}`}>
                      <b>{reaction.label || reaction.reaction || "事件"}</b>
                      <small>{Number(reaction.count || 0).toLocaleString("zh-CN")} 例共报告</small>
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
            <footer>
              {[risk.source, risk.sourceTier, risk.confidence].filter(Boolean).join(" · ") || "来源未记录"}
            </footer>
          </details>
        ))}
      </div>
      {!risks.length ? (
        <EmptyState
          icon={<CheckCircle2 size={30} />}
          title="当前无已触发风险"
          description="没有命中不等于安全；未覆盖组合会保持未知。"
        />
      ) : null}
    </div>
  );
}
