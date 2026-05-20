import { ListPlus, Plus, Trash2 } from "lucide-react";
import { EmptyState } from "../components/EmptyState";
import { formatJournalEntry } from "../lib/format";
import type { JournalEntry } from "../types";

export function JournalPage({
  journal,
  onAdd,
  onDelete,
  onClear,
}: {
  journal: JournalEntry[];
  onAdd: () => void;
  onDelete: (id: string) => void;
  onClear: () => void;
}) {
  return (
    <div className="page-stack">
      <div className="action-row">
        <button className="primary-action" type="button" onClick={onAdd}>
          <Plus size={18} />
          新增摄入
        </button>
        <button className="secondary-action" type="button" onClick={onClear} disabled={!journal.length}>
          <Trash2 size={17} />
          清空
        </button>
      </div>
      <div className="list">
        {journal.map((entry) => (
          <article key={entry.id} className="swipe-row">
            <div className="list-card">
              <div>
                <strong>{entry.substanceName}</strong>
                <span>{new Date(entry.timestamp).toLocaleString("zh-CN")}</span>
                <p>{formatJournalEntry(entry)}</p>
                {entry.note ? <p>{entry.note}</p> : null}
              </div>
              <button className="journal-delete-button" type="button" aria-label="删除日志" onClick={() => onDelete(entry.id)}>
                <Trash2 size={16} />
              </button>
            </div>
          </article>
        ))}
      </div>
      {!journal.length ? (
        <EmptyState
          icon={<ListPlus size={30} />}
          title="还没有摄入日志"
          description="日志只保存在本机 IndexedDB，不会写入静态 API。"
        />
      ) : null}
    </div>
  );
}
