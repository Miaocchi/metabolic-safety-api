import { clippedText } from "../lib/format";

export function EvidenceCard({ row, textField }: { row: Record<string, unknown>; textField?: string }) {
  const primaryText = textField && row[textField] ? row[textField] : row.text || row.evidence || row.note || row.mechanism_of_action || row.effect_text;
  return (
    <article className="evidence-card">
      <strong>{String(row.section || row.source_name || row.source_key || "证据")}</strong>
      <span>{[row.source_name, row.source_tier, row.confidence].filter(Boolean).join(" · ")}</span>
      <p>{clippedText(primaryText, 220)}</p>
    </article>
  );
}
