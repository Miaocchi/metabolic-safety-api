import { riskClass, riskLabel } from "../lib/format";
import type { RiskLevel } from "../types";

export function RiskBadge({ level }: { level?: RiskLevel }) {
  return <span className={`risk-badge ${riskClass(level)}`}>{riskLabel(level)}</span>;
}
