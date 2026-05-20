import { formatNumber } from "../lib/format";

export function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="metric-card">
      <span>{label}</span>
      <strong>{formatNumber(value)}</strong>
    </div>
  );
}
