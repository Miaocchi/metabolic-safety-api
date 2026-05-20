import { BookOpen, Search, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { EmptyState } from "../components/EmptyState";
import { InlineLoading } from "../components/InlineLoading";
import { Metric } from "../components/Metric";
import { Notice } from "../components/Notice";
import { ApiClient } from "../lib/api";
import { displayName, subName } from "../lib/format";
import type { ApiManifest, SubstanceBundle, SubstanceSummary } from "../types";

export function SearchPage({
  api,
  manifest,
  onOpenBundle,
  selectedBundle,
}: {
  api: ApiClient;
  manifest: ApiManifest | null;
  onOpenBundle: (item: SubstanceSummary) => Promise<SubstanceBundle>;
  selectedBundle: SubstanceBundle | null;
}) {
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<SubstanceSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [openingId, setOpeningId] = useState("");
  const openingRef = useRef("");

  const handleOpen = useCallback(
    async (item: SubstanceSummary) => {
      if (openingRef.current) return;
      openingRef.current = item.id;
      setOpeningId(item.id);
      try {
        await onOpenBundle(item);
        setError("");
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        openingRef.current = "";
        setOpeningId("");
      }
    },
    [onOpenBundle],
  );

  useEffect(() => {
    const q = query.trim();
    const handle = window.setTimeout(() => {
      if (!q) {
        setRows([]);
        return;
      }
      setLoading(true);
      api
        .search(q)
        .then((result) => {
          setRows(result);
          setError("");
        })
        .catch((err) => setError(err.message || String(err)))
        .finally(() => setLoading(false));
    }, 180);
    return () => window.clearTimeout(handle);
  }, [api, query]);

  const counts = manifest?.counts || {};
  return (
    <div className="page-stack">
      <div className="search-field">
        <Search size={18} />
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="药物、中文名、英文名或 ID" />
        {query ? (
          <button type="button" onClick={() => setQuery("")} aria-label="清空搜索">
            <X size={16} />
          </button>
        ) : null}
      </div>

      <div className="metric-row">
        <Metric label="实体" value={counts.substances || 0} />
        <Metric label="相互作用" value={counts.interactions || 0} />
        <Metric label="剂量候选" value={counts.dose_candidates || 0} />
      </div>

      {error ? <Notice tone="danger" title="搜索失败" body={error} /> : null}
      {!query ? (
        <EmptyState
          icon={<BookOpen size={30} />}
          title="静态 API 分片检索"
          description="输入关键词后按需读取分片；已打开的详情会缓存到本机。"
        />
      ) : null}
      {loading ? <InlineLoading label="读取搜索分片" /> : null}
      <div className="list">
        {rows.map((item) => {
          const isOpening = openingId === item.id;
          return (
            <button
              key={item.id}
              className="list-card touch-card"
              type="button"
              disabled={isOpening}
              onClick={() => handleOpen(item)}
              onTouchEnd={(event) => {
                event.preventDefault();
                handleOpen(item);
              }}
            >
              <div>
                <strong>{displayName(item)}</strong>
                <span>{subName(item) || item.category || "静态 API 实体"}</span>
              </div>
              <small>{isOpening ? "读取中..." : item.category || "Unknown"}</small>
            </button>
          );
        })}
      </div>
      {selectedBundle ? (
        <div className="summary-card">
          <span>最近打开</span>
          <strong>{displayName(selectedBundle.detail)}</strong>
          <p>
            {selectedBundle.interactions.length} 条相互作用 · {selectedBundle.doseRules.length} 条剂量规则 ·{" "}
            {selectedBundle.overdoseWarnings.length} 条过量警告
          </p>
        </div>
      ) : null}
    </div>
  );
}
