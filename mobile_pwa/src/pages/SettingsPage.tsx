import { ChevronDown, ChevronLeft, Database, Download, Import, Loader2, QrCode } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Grouped } from "../components/Grouped";
import { NumberRow } from "../components/NumberRow";
import { ApiClient } from "../lib/api";
import { clearStaticDatabase, getStaticDbStats } from "../lib/db";
import { displayName } from "../lib/format";
import { COMMON_SHARD_KEYS } from "../services/data-package-manager";
import type { ApiManifest, JournalEntry, PwaSettings, StaticDbStats, SubstanceBundle, SubstanceSummary, UserProfile } from "../types";

/**
 * Transfer payload preview — local-only, never sends data to third-party QR services.
 * Shows the MSAFE1 text payload and offers copy/download actions.
 */
function TransferPayloadPreview({ text, onStatus }: { text: string; onStatus: (msg: string) => void }) {
  const payloadSize = useMemo(() => {
    try {
      return new Blob([text]).size;
    } catch {
      return text.length;
    }
  }, [text]);

  function copyPayload() {
    navigator.clipboard?.writeText(text).then(
      () => onStatus("已复制传输文本到剪贴板"),
      () => onStatus("复制失败，请手动选择文本复制"),
    );
  }

  function downloadPayload() {
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `msafe-transfer-${new Date().toISOString().slice(0, 10)}.txt`;
    anchor.rel = "noopener";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    onStatus("已下载传输文件");
  }

  return (
    <div className="transfer-payload-preview">
      <div className="transfer-payload-actions">
        <button className="secondary-action" type="button" onClick={copyPayload}>
          复制文本
        </button>
        <button className="secondary-action" type="button" onClick={downloadPayload}>
          下载文件
        </button>
      </div>
      <p className="compat-note">
        {`传输大小：${(payloadSize / 1024).toFixed(1)} KB · 传输数据仅存于本设备，不发送到外部服务器。请复制文本或下载文件后在另一设备导入。`}
      </p>
    </div>
  );
}

export function SettingsPage({
  settings,
  profile,
  journal,
  manifest,
  bundles,
  onSaveSettings,
  onSaveProfile,
  onImportTransfer,
  onRefreshJournal,
  onSetBundles,
  onStatus,
}: {
  settings: PwaSettings;
  profile: UserProfile;
  journal: JournalEntry[];
  manifest: ApiManifest | null;
  bundles: Record<string, SubstanceBundle>;
  onSaveSettings: (settings: PwaSettings) => Promise<void>;
  onSaveProfile: (profile: UserProfile) => Promise<void>;
  onImportTransfer: (payload: { profile?: Partial<UserProfile>; journal?: JournalEntry[] }) => Promise<void>;
  onRefreshJournal: () => Promise<void>;
  onSetBundles: (updater: (current: Record<string, SubstanceBundle>) => Record<string, SubstanceBundle>) => void;
  onStatus: (message: string) => void;
}) {
  const BUILTIN_API = "https://miaocchi.github.io/metabolic-safety-api/api";
  const [provider, setProvider] = useState<PwaSettings["remoteProvider"]>(settings.remoteProvider || "github");
  const [remoteApiBase, setRemoteApiBase] = useState(settings.apiBase.startsWith("/") ? "" : settings.apiBase);
  const [draftProfile, setDraftProfile] = useState(profile);
  const [dbStats, setDbStats] = useState<StaticDbStats | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [transferText, setTransferText] = useState("");
  const [settingsView, setSettingsView] = useState<"home" | "database">("home");

  useEffect(() => {
    setProvider(settings.remoteProvider || (settings.apiBase.includes("pages.dev") ? "cloudflare" : "github"));
    setRemoteApiBase(settings.apiBase.startsWith("/") ? "" : settings.apiBase);
  }, [settings]);
  useEffect(() => setDraftProfile(profile), [profile]);
  useEffect(() => {
    getStaticDbStats().then(setDbStats).catch(() => setDbStats(null));
  }, []);

  const packageBytes = manifest?.online_library?.full_package?.zip_bytes || manifest?.full_package?.zip_bytes || 0;
  const packagePath = manifest?.online_library?.full_package?.zip || manifest?.full_package?.zip || "";
  const packageUrl = packagePath ? `${(remoteApiBase.trim() || settings.apiBase || BUILTIN_API).replace(/\/+$/, "")}/${String(packagePath).replace(/^\/?api\//, "").replace(/^\//, "")}` : "";
  const providerPlaceholder =
    provider === "cloudflare" ? "https://<project>.pages.dev/api" : "https://<user>.github.io/<repo>/api";
  async function saveRemoteApi() {
    const trimmed = remoteApiBase.trim().replace(/\/+$/, "");
    const effective = trimmed || BUILTIN_API;
    if (effective.startsWith("http://")) {
      const proceed = window.confirm("当前使用 HTTP（非 HTTPS）连接远程 API，搜索内容和物质名称将可能以明文传输并被中间人读取。是否继续？");
      if (!proceed) return;
    }
    await onSaveSettings({
      ...settings,
      remoteProvider: provider,
      apiBase: effective,
      localBackendEnabled: false,
      staticDbMode: "local-first",
    });
    onStatus(trimmed ? `已设置 ${provider === "cloudflare" ? "Cloudflare Pages" : "GitHub Pages"} 远程数据库` : `已恢复内置数据库：${BUILTIN_API}`);
  }

  async function syncDatabase() {
    setSyncing(true);
    try {
      const result = await new ApiClient(remoteApiBase.trim() || settings.apiBase || BUILTIN_API, settings.localApiBase).syncLocalDatabase();
      const stats = await getStaticDbStats();
      setDbStats(stats);
      onStatus(`本地数据库已同步 · ${result.shardKeys.length} 个搜索分片 · ${result.manifest.dataset_version || "未知版本"}`);
    } catch (error) {
      onStatus(error instanceof Error ? error.message : String(error));
    } finally {
      setSyncing(false);
    }
  }

  async function clearLocalDb() {
    await clearStaticDatabase();
    setDbStats(await getStaticDbStats());
    onStatus("已清空本地静态数据库缓存");
  }

  function buildTransferPayload() {
    const substances = Object.fromEntries(
      journal
        .map((entry) => entry.substanceSnapshot || { id: entry.substanceId, name_zh: entry.substanceName, name_en: entry.substanceName })
        .filter((item): item is SubstanceSummary => Boolean(item?.id))
        .map((item) => [item.id, item]),
    );
    return `MSAFE1:${btoa(unescape(encodeURIComponent(JSON.stringify({
      version: 1,
      createdAt: Date.now(),
      profile: draftProfile,
      substances,
      journal: journal.map((entry) => ({
        ...entry,
        substanceName: entry.substanceName || displayName(entry.substanceSnapshot) || entry.substanceId,
        substanceSnapshot: entry.substanceSnapshot || substances[entry.substanceId],
      })),
    }))))}`;
  }

  function exportTransfer() {
    const payload = buildTransferPayload();
    setTransferText(payload);
    navigator.clipboard?.writeText(payload).catch(() => undefined);
    onStatus("已生成传输文本，可复制或下载后在另一设备导入");
  }

  async function importTransfer() {
    const text = transferText.trim();
    if (!text) return onStatus("请先粘贴扫码得到的导入文本");
    try {
      const raw = text.startsWith("MSAFE1:") ? text.slice("MSAFE1:".length) : text;
      const payload = JSON.parse(decodeURIComponent(escape(atob(raw))));
      await onImportTransfer({ profile: payload.profile, journal: Array.isArray(payload.journal) ? payload.journal : [] });
    } catch (error) {
      onStatus(`导入失败：${error instanceof Error ? error.message : String(error)}`);
    }
  }

  function downloadOfflinePackage() {
    if (!packageUrl) {
      onStatus("当前 manifest 未提供全量离线包地址");
      return;
    }
    const anchor = document.createElement("a");
    anchor.href = packageUrl;
    anchor.download = packagePath.split("/").pop() || "metabolic-safety-api.zip";
    anchor.rel = "noopener";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    onStatus("已开始下载全量离线包");
  }

  if (settingsView === "database") {
    return (
      <div className="page-stack settings-page">
        <button className="subpage-back" type="button" onClick={() => setSettingsView("home")}>
          <ChevronLeft size={18} />
          返回设置
        </button>
        <Grouped title="本地数据库">
          <div className="db-status-grid">
            <div>
              <span>JSON 文件</span>
              <strong>{dbStats?.jsonFiles ?? 0}</strong>
            </div>
            <div>
              <span>搜索分片</span>
              <strong>{dbStats?.searchShards ?? 0}</strong>
            </div>
            <div>
              <span>详情缓存</span>
              <strong>{dbStats?.bundles ?? 0}</strong>
            </div>
          </div>
          <div className="compat-note">
            {dbStats?.lastSyncAt
              ? `最近同步：${new Date(dbStats.lastSyncAt).toLocaleString("zh-CN")} · ${dbStats.datasetVersion || "未知版本"}`
              : settings.autoSyncOnLaunch !== false
                ? "本地缓存为空，下次启动时将自动同步权威数据库索引。也可手动同步。"
                : "本地数据库会随搜索和详情读取逐步建立，也可以从远程数据库手动同步常用索引。"}
          </div>
          <div className="db-actions">
            <button className="primary-action full" type="button" onClick={syncDatabase} disabled={syncing}>
              {syncing ? <Loader2 className="spin" size={18} /> : <Download size={18} />}
              同步本地数据库
            </button>
            <button className="secondary-action full" type="button" onClick={clearLocalDb}>
              清空本地库
            </button>
          </div>
        </Grouped>

        <Grouped title="远程数据库">
          <div className="provider-toggle" role="group" aria-label="远程 API 类型">
            <button className={provider === "github" ? "active" : ""} type="button" onClick={() => setProvider("github")}>
              GitHub Pages
            </button>
            <button className={provider === "cloudflare" ? "active" : ""} type="button" onClick={() => setProvider("cloudflare")}>
              Cloudflare Pages
            </button>
          </div>
          <label className="setting-block">
            <span>{provider === "cloudflare" ? "Cloudflare Pages API" : "GitHub Pages API"}</span>
            <input value={remoteApiBase} placeholder={providerPlaceholder} onChange={(event) => setRemoteApiBase(event.target.value)} />
          </label>
          {remoteApiBase.trim() && !remoteApiBase.trim().startsWith("https://") && (
            <div className="compat-note" style={{ color: "#b45309" }}>
              建议使用 HTTPS 地址。HTTP 连接下，搜索词和物质名称可能以明文传输，被网络中间方读取。
            </div>
          )}
          <div className="compat-note">
            内置源：{BUILTIN_API}。留空时自动使用内置源；也可填写自己的 GitHub/Cloudflare Pages 静态 JSON API。
            <br />
            <strong>隐私提示：</strong>搜索物质名称和 ID 会发送到上述远程 API 所在主机。
          </div>
          <div className="db-actions single">
            <button className="primary-action full" type="button" onClick={saveRemoteApi}>
              保存远程数据库
            </button>
          </div>
        </Grouped>

        <Grouped title="离线包">
          <button className="download-card touch-card" type="button" onClick={downloadOfflinePackage}>
            <Download size={19} />
            <div>
              <strong>全量包入口</strong>
              <span>{packageBytes ? `${(packageBytes / 1024 / 1024).toFixed(1)} MB · 点击下载` : "未发现全量包"}</span>
            </div>
          </button>
        </Grouped>

        <Grouped title="启动同步">
          <label className="setting-row">
            <span>启动时自动同步权威数据库</span>
            <input
              type="checkbox"
              checked={settings.autoSyncOnLaunch !== false}
              onChange={(event) =>
                onSaveSettings({ ...settings, autoSyncOnLaunch: event.target.checked })
              }
            />
          </label>
          <div className="compat-note">
            开启后，首次启动或本地缓存为空时，自动从远程 Pages API 拉取 manifest 和常用搜索分片（{COMMON_SHARD_KEYS.join("、")}）。
            这些是权威预生成的静态 JSON 文件，不含个人数据。关闭后仅在手动点击"同步本地数据库"时更新。
            <br />
            <strong>隐私说明：</strong>同步仅下载公开静态索引文件，不会上传日志、个人参数或任何用户数据。
          </div>
        </Grouped>
      </div>
    );
  }

  return (
    <div className="page-stack settings-page">
      <Grouped title="数据库">
        <button className="settings-nav-card touch-card" type="button" onClick={() => setSettingsView("database")}>
          <Database size={20} />
          <div>
            <strong>本地 / 远程数据库</strong>
            <span>
              {dbStats?.lastSyncAt
                ? `${dbStats.datasetVersion || "已同步"} · ${dbStats.searchShards ?? 0} 个分片`
                : settings.autoSyncOnLaunch !== false
                  ? "启动时自动同步 · 点击查看详情"
                  : "同步缓存、远程 API、离线包"}
            </span>
          </div>
          <ChevronDown size={17} />
        </button>
      </Grouped>

      <Grouped title="个人参数">
        <NumberRow label="体重 kg" value={draftProfile.weightKg} onChange={(weightKg) => setDraftProfile({ ...draftProfile, weightKg })} />
        <NumberRow label="身高 cm" value={draftProfile.heightCm} onChange={(heightCm) => setDraftProfile({ ...draftProfile, heightCm })} />
        <NumberRow label="年龄" value={draftProfile.ageYears} onChange={(ageYears) => setDraftProfile({ ...draftProfile, ageYears })} />
        <NumberRow label="体脂 %" value={draftProfile.bodyFatPct} onChange={(bodyFatPct) => setDraftProfile({ ...draftProfile, bodyFatPct })} />
        <NumberRow label="睡眠不足 h" value={draftProfile.sleepDebtHours} onChange={(sleepDebtHours) => setDraftProfile({ ...draftProfile, sleepDebtHours })} />
        <NumberRow label="体温 °C" value={draftProfile.coreTempC} onChange={(coreTempC) => setDraftProfile({ ...draftProfile, coreTempC })} />
        <label className="setting-row">
          <span>代谢表型</span>
          <select
            value={draftProfile.metabolicType}
            onChange={(event) => setDraftProfile({ ...draftProfile, metabolicType: event.target.value as UserProfile["metabolicType"] })}
          >
            <option value="UM">超快代谢</option>
            <option value="EM">正常代谢</option>
            <option value="IM">中间代谢</option>
            <option value="PM">慢代谢</option>
          </select>
        </label>
        <button className="primary-action full" type="button" onClick={() => onSaveProfile(draftProfile)}>
          保存参数
        </button>
      </Grouped>

      <Grouped title="二维码迁移">
        <div className="qr-transfer-card">
          <div className="qr-actions">
            <button className="primary-action full" type="button" onClick={exportTransfer}>
              <QrCode size={18} />
              生成传输文本
            </button>
            <button className="secondary-action full" type="button" onClick={importTransfer}>
              <Import size={18} />
              导入
            </button>
          </div>
          {transferText ? <TransferPayloadPreview text={transferText} onStatus={onStatus} /> : null}
          <textarea value={transferText} onChange={(event) => setTransferText(event.target.value)} placeholder="这里会生成传输 payload；也可粘贴另一端导出的 MSAFE1 文本后导入" rows={5} />
          <p>包含个人参数和摄入日志；不包含静态药物数据库。传输数据仅在本设备处理，不发送到外部服务器。</p>
        </div>
      </Grouped>

      <Grouped title="不良事件信号">
        <label className="setting-row">
          <span>实时 openFDA 信号回退</span>
          <input
            type="checkbox"
            checked={!!settings.liveSignalsEnabled}
            onChange={(event) =>
              onSaveSettings({ ...settings, liveSignalsEnabled: event.target.checked })
            }
          />
        </label>
        <div className="compat-note">
          默认关闭。开启后，当本地缓存没有静态不良事件信号时，会向 openFDA（api.fda.gov）发送物质名称查询。
          这会将您日志中的物质名称暴露给第三方 API。关闭时仅使用预生成的静态信号数据。
        </div>
      </Grouped>
    </div>
  );
}
