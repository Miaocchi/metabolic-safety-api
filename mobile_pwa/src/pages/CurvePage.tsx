import { Activity, ChevronDown, Gauge, Plus, ShieldAlert } from "lucide-react";
import { PointerEvent, useEffect, useMemo, useRef, useState } from "react";
import { riskLabel, riskSortValue } from "../lib/format";
import { buildCurveModel, calculateFullPMI, calculatePMI, pmiLabel } from "../lib/pk";
import type { JournalEntry, RiskEvent, SubstanceBundle, UserProfile } from "../types";

function fmtNumber(value: number, digits = 3) {
  if (!Number.isFinite(value)) return "0";
  return value.toFixed(digits);
}

function fmtDuration(minutes: number) {
  if (minutes < 1) return "<1分钟";
  if (minutes < 60) return `${Math.round(minutes)}分钟`;
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return m > 0 ? `${h}小时${m}分钟` : `${h}小时`;
}

export function CurvePage({ entries, bundles, profile, risks, onAddEntry, onGotoRisks }: { entries: JournalEntry[]; bundles: Record<string, SubstanceBundle>; profile: UserProfile; risks: RiskEvent[]; onAddEntry: () => void; onGotoRisks: () => void }) {
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState(0);
  const [selectedCurveId, setSelectedCurveId] = useState("all");
  const curveEntries = useMemo(() => (selectedCurveId === "all" ? entries : entries.filter((entry) => entry.substanceId === selectedCurveId)), [entries, selectedCurveId]);
  const curveOptions = useMemo(() => [...new Map(entries.map((entry) => [entry.substanceId, entry.substanceName])).entries()], [entries]);
  const model = useMemo(() => buildCurveModel(curveEntries, bundles, profile, zoom, offset), [bundles, curveEntries, offset, profile, zoom]);
  const pmi = useMemo(() => calculateFullPMI(entries, bundles, profile, risks), [entries, bundles, profile, risks]);
  const baselinePmi = useMemo(() => calculatePMI(profile), [profile]);
  const baselineLabel = useMemo(() => pmiLabel(baselinePmi.value), [baselinePmi]);
  const highRisks = useMemo(() => risks.filter((risk) => riskSortValue(risk.level) >= riskSortValue("Major")), [risks]);
  const leadRisk = highRisks[0] || risks[0];

  const hasEntries = entries.length > 0;
  const hasActiveExposure = pmi.activeCount > 0;

  useEffect(() => {
    if (selectedCurveId !== "all" && !curveOptions.some(([id]) => id === selectedCurveId)) setSelectedCurveId("all");
  }, [curveOptions, selectedCurveId]);

  return (
    <div className="page-stack">
      {/* Risk alert banner — only when there are active risks */}
      {leadRisk ? (
        <button
          type="button"
          className={`risk-alert-card touch-card ${highRisks.length ? "critical" : "watch"}`}
          onClick={onGotoRisks}
        >
          <div className="risk-alert-icon">
            <ShieldAlert size={22} />
          </div>
          <div>
            <span>{highRisks.length ? `${highRisks.length} 个高优先级风险` : "风险提示"}</span>
            <strong>{riskLabel(leadRisk.level)} · {leadRisk.title}</strong>
            <small>{leadRisk.subtitle || leadRisk.note || "点击查看风险详情"}</small>
          </div>
          <ChevronDown size={18} />
        </button>
      ) : null}

      {/* Baseline PMI — always visible, even with no entries */}
      {!hasEntries || !hasActiveExposure ? (
        <div className="pmi-baseline-card">
          <div className="pmi-gauge">
            <div className="pmi-score" style={{ color: baselineLabel.color }}>{baselinePmi.value}</div>
            <div>
              <strong>{baselineLabel.label}</strong>
              <span>
                {hasEntries
                  ? `暂无活跃暴露 · ${entries.length} 条历史日志 · 代谢基线由个人参数计算`
                  : "暂无摄入记录 · 代谢基线由个人参数计算"}
              </span>
            </div>
          </div>
          <div className="pmi-bars">
            <div><span>代谢表型</span><strong>{baselinePmi.phenotypeFactor.toFixed(2)}</strong></div>
            <div><span>体温因子</span><strong>{baselinePmi.tempFactor.toFixed(2)}</strong></div>
            <div><span>睡眠因子</span><strong>{baselinePmi.sleepFactor.toFixed(2)}</strong></div>
            <div><span>BMI 因子</span><strong>{baselinePmi.bmiFactor.toFixed(2)}</strong></div>
          </div>
          <div className="pmi-baseline-note">
            <span>PMI = {baselinePmi.value} · BMI {baselinePmi.bmi.toFixed(1)} · 半衰期倍率 {(baselinePmi.raw / 100).toFixed(2)}x</span>
          </div>
          <div className="pmi-baseline-cta">
            <button className="primary-action" type="button" onClick={onAddEntry}>
              <Plus size={18} />
              {hasEntries ? "新增摄入" : "记录第一次摄入"}
            </button>
          </div>
        </div>
      ) : null}

      {/* Full PMI + Curve — only when there are active entries */}
      {hasEntries && hasActiveExposure ? (
        <>
          {/* PMI Summary */}
          <div className={`pmi-summary level-${pmi.levelClass}`}>
            <div className="pmi-gauge">
              <div className="pmi-score">{pmi.pmi}</div>
              <div>
                <strong>{pmi.level}</strong>
                <span>总暴露 {fmtNumber(pmi.totalExposure, 3)} · 向后暴露指数 {pmi.forwardIndex}/100 · 活跃 {pmi.activeCount} 项 / {pmi.substanceCount} 种</span>
              </div>
            </div>
            <div className="pmi-bars pmi-bars-detailed">
              <div><span>冲突/过量</span><strong>{Math.round(pmi.riskScore)}</strong></div>
              <div><span>当前暴露</span><strong>{Math.round(pmi.exposureScore)}</strong></div>
              <div><span>未来暴露</span><strong>{Math.round(pmi.forwardScore)}</strong></div>
              <div><span>个体脆弱性</span><strong>{Math.round(pmi.modifierScore)}</strong></div>
              <div><span>用药复杂度</span><strong>{Math.round(pmi.complexityScore)}</strong></div>
            </div>
            <div className="pmi-table">
              {pmi.rows.slice(0, 4).map((row, i) => (
                <div key={i} className="pmi-row">
                  <span>{row.name}</span>
                  <strong>{fmtNumber(row.exposure, 3)}</strong>
                  <small>{row.count && row.count > 1 ? `×${row.count} · ` : ""}t1/2 {row.halfLife.toFixed(1)}h · Cmax {fmtNumber(row.cmax, 3)}</small>
                </div>
              ))}
            </div>
            <div className="pmi-forward">
              <div className="pmi-forward-head">
                <strong>向后暴露指数</strong>
                <span>未来 24h AUC / 峰值 / 达峰时间</span>
              </div>
              <div className="pmi-forward-list">
                {pmi.forwardRows.length === 0 && (
                  <div className="pmi-forward-empty">未检出未来 24h 的明显剩余暴露。</div>
                )}
                {pmi.forwardRows.map((row) => {
                  const unitText = row.unit === "mixed" ? "mixed/L" : `${row.unit}/L`;
                  const peakTime = row.minutesToPeak > 0 ? `${fmtDuration(row.minutesToPeak)}后达峰` : "已在高位/已过峰";
                  return (
                    <div key={row.id} className="pmi-forward-row">
                      <div className="pmi-forward-drug"><span>{row.name}</span></div>
                      <div className="pmi-forward-count"><span>×{row.count}</span></div>
                      <div className="pmi-forward-peak"><small>{peakTime}</small></div>
                      <strong>{row.index}</strong>
                      <small>AUC24 {fmtNumber(row.auc24, row.auc24 < 1 ? 3 : 1)} · peak {fmtNumber(row.peak, row.peak < 1 ? 3 : 2)} {unitText}</small>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Curve filter */}
          <div className="curve-filter" role="group" aria-label="选择代谢曲线">
            <button type="button" className={selectedCurveId === "all" ? "active" : ""} onClick={() => setSelectedCurveId("all")}>
              全部
            </button>
            {curveOptions.map(([id, name]) => (
              <button key={id} type="button" className={selectedCurveId === id ? "active" : ""} onClick={() => setSelectedCurveId(id)}>
                {name}
              </button>
            ))}
          </div>
          <div className="curve-shell">
            <CurveCanvas model={model} onPan={(delta) => setOffset((value) => value + delta)} />
          </div>
          <div className="curve-controls">
            <button type="button" onClick={() => setOffset((value) => value - 1)}>
              -1h
            </button>
            <input type="range" min="0.5" max="4" step="0.25" value={zoom} onChange={(event) => setZoom(Number(event.target.value))} />
            <button type="button" onClick={() => setOffset((value) => value + 1)}>
              +1h
            </button>
          </div>
          <div className="curve-zoom-label">
            <span>{selectedCurveId === "all" ? "全部活跃曲线" : "单药曲线"}</span>
            <strong>{zoom.toFixed(2)}x</strong>
          </div>
          <div className="list compact">
            {model.series.map((series) => (
              <div key={series.id} className="legend-row">
                <i style={{ background: series.color }} />
                <span>{series.label}</span>
                <strong>{series.current.toFixed(series.current < 1 ? 3 : 2)} mg/L</strong>
              </div>
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}

function CurveCanvas({ model, onPan }: { model: ReturnType<typeof buildCurveModel>; onPan: (hours: number) => void }) {
  const ref = useRef<HTMLCanvasElement | null>(null);
  const startX = useRef<number | null>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = Math.max(1, Math.floor(rect.width * dpr));
    canvas.height = Math.max(1, Math.floor(rect.height * dpr));
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);
    const styles = getComputedStyle(document.documentElement);
    const text = styles.getPropertyValue("--text").trim() || "#111827";
    const muted = styles.getPropertyValue("--muted").trim() || "#6b7280";
    const line = styles.getPropertyValue("--line").trim() || "#d1d5db";
    const card = styles.getPropertyValue("--card-solid").trim() || "#ffffff";
    const blue = styles.getPropertyValue("--blue").trim() || "#007aff";
    const red = styles.getPropertyValue("--red").trim() || "#ff3b30";
    ctx.fillStyle = card;
    ctx.fillRect(0, 0, width, height);
    const left = 42 * dpr;
    const right = 16 * dpr;
    const top = 20 * dpr;
    const bottom = 38 * dpr;
    const plotW = width - left - right;
    const plotH = height - top - bottom;
    ctx.strokeStyle = line;
    ctx.lineWidth = 1 * dpr;
    ctx.beginPath();
    for (let i = 0; i <= 4; i += 1) {
      const y = top + plotH * (i / 4);
      ctx.moveTo(left, y);
      ctx.lineTo(left + plotW, y);
    }
    for (let i = 0; i <= 6; i += 1) {
      const x = left + plotW * (i / 6);
      ctx.moveTo(x, top);
      ctx.lineTo(x, top + plotH);
    }
    ctx.stroke();
    ctx.fillStyle = muted;
    ctx.font = `${11 * dpr}px -apple-system, BlinkMacSystemFont, sans-serif`;
    for (let i = 0; i <= 4; i += 1) {
      const value = model.maxY * (1 - i / 4);
      const y = top + plotH * (i / 4) + 4 * dpr;
      ctx.fillText(value.toFixed(value < 1 ? 2 : 1), 8 * dpr, y);
    }

    const drawLine = (points: Array<{ x: number; y: number }>, color: string, widthPx: number) => {
      if (!points.length) return;
      ctx.strokeStyle = color;
      ctx.lineWidth = widthPx * dpr;
      ctx.lineJoin = "round";
      ctx.lineCap = "round";
      ctx.beginPath();
      points.forEach((point, index) => {
        const x = left + plotW * point.x;
        const y = top + plotH - plotH * (point.y / model.maxY);
        if (index === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    };

    const drawArea = (points: Array<{ x: number; y: number }>, color: string) => {
      if (!points.length) return;
      const gradient = ctx.createLinearGradient(0, top, 0, top + plotH);
      gradient.addColorStop(0, `${color}44`);
      gradient.addColorStop(1, `${color}05`);
      ctx.fillStyle = gradient;
      ctx.beginPath();
      points.forEach((point, index) => {
        const x = left + plotW * point.x;
        const y = top + plotH - plotH * (point.y / model.maxY);
        if (index === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.lineTo(left + plotW, top + plotH);
      ctx.lineTo(left, top + plotH);
      ctx.closePath();
      ctx.fill();
    };

    drawArea(model.total, blue);
    drawLine(model.total, text, 2.4);
    model.series.forEach((series) => drawLine(series.points, series.color, 1.8));
    const nowX = left + plotW * ((Date.now() - model.start) / Math.max(model.end - model.start, 1));
    ctx.strokeStyle = red;
    ctx.lineWidth = 1.5 * dpr;
    ctx.setLineDash([4 * dpr, 4 * dpr]);
    ctx.beginPath();
    ctx.moveTo(nowX, top);
    ctx.lineTo(nowX, top + plotH);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = text;
    ctx.fillText(new Date(model.start).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }), left, height - 14 * dpr);
    ctx.fillText("现在", Math.min(Math.max(nowX - 10 * dpr, left), left + plotW - 26 * dpr), top - 6 * dpr);
    ctx.textAlign = "right";
    ctx.fillText(new Date(model.end).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }), width - right, height - 14 * dpr);
    ctx.textAlign = "left";
  }, [model]);

  function pointerDown(event: PointerEvent<HTMLCanvasElement>) {
    startX.current = event.clientX;
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function pointerUp(event: PointerEvent<HTMLCanvasElement>) {
    if (startX.current === null) return;
    const delta = event.clientX - startX.current;
    if (Math.abs(delta) > 30) onPan(delta > 0 ? -1 : 1);
    startX.current = null;
  }

  return <canvas ref={ref} className="curve-canvas" onPointerDown={pointerDown} onPointerUp={pointerUp} />;
}
