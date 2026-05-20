import { Loader2, Plus, Search } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { ApiClient } from "../lib/api";
import { displayName, dateTimeLocalToTimestamp, subName, toDateTimeLocal, routeLabel } from "../lib/format";
import type { JournalEntry, RouteKey, StomachState, SubstanceBundle, SubstanceSummary } from "../types";

function makeId(prefix = "entry") {
  return `${prefix}_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function doseHelperKind(item: SubstanceSummary | null) {
  const name = item ? `${displayName(item)} ${subName(item)} ${item.id}`.toLowerCase() : "";
  if (/东方树叶|茶多酚|polyphenol|tea/.test(name)) return "tea";
  if (/酒精|乙醇|ethanol|alcohol|beer|wine|liquor|白酒|啤酒|葡萄酒|威士忌/.test(name)) return "alcohol";
  return "";
}

function alcoholGrams(volumeMl: number, abvPct: number) {
  return Math.max(0, volumeMl) * Math.max(0, abvPct) / 100 * 0.789;
}

function orientalLeafPolyphenolMg(volumeMl: number) {
  return Math.max(0, volumeMl) * 0.28;
}

export function EntrySheetContent({
  api,
  onAdd,
  onBundle,
  onClose,
}: {
  api: ApiClient;
  onAdd: (entry: JournalEntry) => void;
  onBundle: (item: SubstanceSummary) => Promise<SubstanceBundle>;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<SubstanceSummary[]>([]);
  const [selected, setSelected] = useState<SubstanceSummary | null>(null);
  const [dose, setDose] = useState(200);
  const [unit, setUnit] = useState("mg");
  const [route, setRoute] = useState<RouteKey>("Oral");
  const [stomach, setStomach] = useState<StomachState>("Light");
  const [time, setTime] = useState(toDateTimeLocal(Date.now()));
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(false);
  const [drinkVolumeMl, setDrinkVolumeMl] = useState(500);
  const [alcoholAbvPct, setAlcoholAbvPct] = useState(5);
  const helperKind = doseHelperKind(selected);

  useEffect(() => {
    if (!query.trim()) {
      setRows([]);
      return;
    }
    const handle = window.setTimeout(() => {
      api.search(query).then(setRows).catch(() => setRows([]));
    }, 180);
    return () => window.clearTimeout(handle);
  }, [api, query]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    setLoading(true);
    try {
      const bundle = await onBundle(selected);
      await onAdd({
        id: makeId(),
        substanceId: bundle.detail.id,
        substanceName: displayName(bundle.detail),
        timestamp: dateTimeLocalToTimestamp(time),
        dosage: dose,
        unit,
        route,
        stomachState: stomach,
        note: note.trim(),
        substanceSnapshot: bundle.detail,
      });
      setSelected(null);
      setQuery("");
      setNote("");
      onClose();
    } finally {
      setLoading(false);
    }
  }

  return (
    <form className="entry-form" onSubmit={submit}>
      <div className="search-field inline">
        <Search size={17} />
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索物质" />
      </div>
      {selected ? <div className="selected-chip">{displayName(selected)}</div> : null}
      <div className="mini-results">
        {rows.slice(0, 8).map((item) => (
          <button key={item.id} type="button" onClick={() => setSelected(item)}>
            <strong>{displayName(item)}</strong>
            <span>{subName(item) || item.category}</span>
          </button>
        ))}
      </div>
      {helperKind ? (
        <div className="dose-helper-card">
          <div className="dose-helper-head">
            <strong>{helperKind === "alcohol" ? "酒精换算" : "东方树叶茶多酚换算"}</strong>
            <span>{helperKind === "alcohol" ? "容量 × 酒精度 × 0.789g/ml" : "按 280mg 茶多酚/kg 饮品估算"}</span>
          </div>
          <div className="dose-helper-grid">
            <label>
              容量 ml
              <input type="number" min="0" step="1" value={drinkVolumeMl} onChange={(event) => setDrinkVolumeMl(Number(event.target.value))} />
            </label>
            {helperKind === "alcohol" ? (
              <label>
                酒精度 %vol
                <input type="number" min="0" step="0.1" value={alcoholAbvPct} onChange={(event) => setAlcoholAbvPct(Number(event.target.value))} />
              </label>
            ) : null}
          </div>
          <button
            type="button"
            className="secondary-action full"
            onClick={() => {
              if (helperKind === "alcohol") {
                setDose(Number(alcoholGrams(drinkVolumeMl, alcoholAbvPct).toFixed(2)));
                setUnit("g");
                return;
              }
              setDose(Number(orientalLeafPolyphenolMg(drinkVolumeMl).toFixed(0)));
              setUnit("mg");
            }}
          >
            写入 {helperKind === "alcohol" ? `${alcoholGrams(drinkVolumeMl, alcoholAbvPct).toFixed(2)} g 酒精` : `${orientalLeafPolyphenolMg(drinkVolumeMl).toFixed(0)} mg 茶多酚`}
          </button>
        </div>
      ) : null}
      <div className="form-grid">
        <label>
          剂量
          <input type="number" min="0" step="0.01" value={dose} onChange={(event) => setDose(Number(event.target.value))} />
        </label>
        <label>
          单位
          <select value={unit} onChange={(event) => setUnit(event.target.value)}>
            <option value="mg">mg</option>
            <option value="ug">ug</option>
            <option value="g">g</option>
            <option value="ml">ml</option>
          </select>
        </label>
        <label>
          时间
          <input type="datetime-local" value={time} onChange={(event) => setTime(event.target.value)} />
        </label>
        <label>
          途径
          <select value={route} onChange={(event) => setRoute(event.target.value as RouteKey)}>
            <option value="Oral">口服</option>
            <option value="Sublingual">舌下</option>
            <option value="Insufflated">鼻腔</option>
            <option value="Topical">经皮</option>
            <option value="IV">静脉/瞬时</option>
            <option value="Other">其他</option>
          </select>
        </label>
        <label>
          胃部状态
          <select value={stomach} onChange={(event) => setStomach(event.target.value as StomachState)}>
            <option value="Light">正常/少量进食</option>
            <option value="Fasting">完全空腹</option>
            <option value="Heavy">高脂重餐</option>
          </select>
        </label>
      </div>
      <label>
        备注
        <textarea value={note} onChange={(event) => setNote(event.target.value)} />
      </label>
      <button className="primary-action full" type="submit" disabled={!selected || loading}>
        {loading ? <Loader2 className="spin" size={18} /> : <Plus size={18} />}
        保存并检查
      </button>
    </form>
  );
}
