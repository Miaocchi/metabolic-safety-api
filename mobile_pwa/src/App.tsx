import {
  Activity,
  Apple,
  Cloud,
  ListPlus,
  Plus,
  Search,
  Settings,
  ShieldAlert,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AdaptiveLayout } from "./components/AdaptiveLayout";
import { AdaptiveTabBar, type TabItem } from "./components/AdaptiveTabBar";
import { BottomSheet } from "./components/BottomSheet";
import { InlineLoading } from "./components/InlineLoading";
import { NavigationBar } from "./components/NavigationBar";
import { PullToRefresh } from "./components/PullToRefresh";
import { EntrySheetContent } from "./components/EntrySheetContent";
import { SubstanceDetailView } from "./components/SubstanceDetailView";
import { SearchPage } from "./pages/SearchPage";
import { JournalPage } from "./pages/JournalPage";
import { RisksPage } from "./pages/RisksPage";
import { CurvePage } from "./pages/CurvePage";
import { SettingsPage } from "./pages/SettingsPage";
import { useHaptics, usePlatform } from "./hooks/usePlatform";
import { ApiClient } from "./lib/api";
import {
  allJournal,
  cacheBundle,
  clearJournal,
  deleteJournalEntry,
  getCachedBundle,
  getCachedBundleIds,
  getStaticDbStats,
  loadProfile,
  loadSettings,
  saveJournalEntry,
  saveProfile,
  saveSettings,
} from "./lib/db";
import { displayName, formatNumber, riskSortValue } from "./lib/format";
import { activeEntries, defaultProfile } from "./lib/pk";
import {
  adverseSignalRisks,
  doseRuleRisks,
  localStaticPairRisks,
  modelRisks,
  overdoseEvidenceRisks,
  sortRisks,
} from "./lib/risks";
import type {
  ApiManifest,
  JournalEntry,
  PwaSettings,
  RiskEvent,
  SubstanceBundle,
  SubstanceSummary,
  UserProfile,
} from "./types";

type TabKey = "search" | "journal" | "risks" | "curve" | "settings";

const defaultSettings: PwaSettings = {
  apiBase: "https://miaocchi.github.io/metabolic-safety-api/api",
  localApiBase: "/local-api",
  cacheMode: "recent",
  localBackendEnabled: false,
  remoteProvider: "github",
  staticDbMode: "local-first",
  liveSignalsEnabled: false,
  autoSyncOnLaunch: true,
};

const tabItems: TabItem[] = [
  { key: "curve", label: "指数", icon: Activity },
  { key: "risks", label: "风险", icon: ShieldAlert },
  { key: "journal", label: "摄入记录", icon: ListPlus },
  { key: "search", label: "搜索", icon: Search },
  { key: "settings", label: "设置", icon: Settings },
];

function makeId(prefix = "entry") {
  return `${prefix}_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

export default function App() {
  const platform = usePlatform();
  const haptics = useHaptics();

  const [activeTab, setActiveTab] = useState<TabKey>("curve");
  const [settings, setSettingsState] = useState(defaultSettings);
  const [profile, setProfileState] = useState<UserProfile>(defaultProfile);
  const [manifest, setManifest] = useState<ApiManifest | null>(null);
  const [journal, setJournal] = useState<JournalEntry[]>([]);
  const [bundles, setBundles] = useState<Record<string, SubstanceBundle>>({});
  const [selectedBundle, setSelectedBundle] = useState<SubstanceBundle | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [entrySheetOpen, setEntrySheetOpen] = useState(false);
  const [status, setStatus] = useState("正在初始化移动端...");
  const [signalRisks, setSignalRisks] = useState<RiskEvent[]>([]);
  const [tabBarHidden, setTabBarHidden] = useState(false);
  const [modelNow, setModelNow] = useState(() => Date.now());

  const api = useMemo(() => new ApiClient(settings.apiBase, settings.localApiBase), [settings.apiBase, settings.localApiBase]);

  const refreshJournal = useCallback(async () => {
    setJournal(await allJournal());
  }, []);

  const hydrateCache = useCallback(async () => {
    const records = await getCachedBundleIds();
    const next: Record<string, SubstanceBundle> = {};
    await Promise.all(
      records.slice(0, 80).map(async (record) => {
        const cached = await getCachedBundle(record.key.replace(/^bundle:/, ""));
        if (cached?.detail?.id) next[cached.detail.id] = cached;
      }),
    );
    setBundles((current) => ({ ...next, ...current }));
  }, []);

  useEffect(() => {
    let alive = true;
    async function boot() {
      const [storedSettings, storedProfile] = await Promise.all([loadSettings().catch(() => undefined), loadProfile().catch(() => undefined)]);
      if (!alive) return;
      if (storedSettings) {
        const apiBase = storedSettings.apiBase || defaultSettings.apiBase;
        setSettingsState({
          ...defaultSettings,
          ...storedSettings,
          apiBase,
          localBackendEnabled: false,
          staticDbMode: storedSettings.staticDbMode || "local-first",
        });
      }
      if (storedProfile) setProfileState({ ...defaultProfile, ...storedProfile });
      await Promise.all([refreshJournal(), hydrateCache()]);
    }
    boot().catch((error) => setStatus(error.message || String(error)));
    return () => {
      alive = false;
    };
  }, [hydrateCache, refreshJournal]);

  useEffect(() => {
    api
      .fetchManifest()
      .then((payload) => {
        setManifest(payload);
        const count = payload.counts?.substances || 0;
        setStatus(`已连接静态 API · ${formatNumber(count)} 个实体`);
      })
      .catch((error) => setStatus(error.message || String(error)));
  }, [api]);

  // Auto-bootstrap: sync authoritative static API shards on first launch when cache is empty.
  // This pulls manifest + common search shards from the configured remote Pages API into
  // IndexedDB, so subsequent searches and substance lookups work offline-first.
  // Privacy: only static JSON endpoints are fetched; no journal/profile data leaves the device.
  useEffect(() => {
    if (!settings.autoSyncOnLaunch) return;
    let cancelled = false;
    (async () => {
      try {
        const stats = await getStaticDbStats();
        if (cancelled) return;
        // Only auto-sync when no prior sync recorded and cache is empty
        if (stats.lastSyncAt || stats.searchShards > 0) return;
        setStatus("首次启动：正在同步权威静态数据库...");
        const result = await api.syncLocalDatabase();
        if (cancelled) return;
        setStatus(`已自动同步 · ${result.shardKeys.length} 个搜索分片 · ${result.manifest.dataset_version || "未知版本"}`);
      } catch (error) {
        if (!cancelled) setStatus(error instanceof Error ? `自动同步失败：${error.message}` : "自动同步失败");
      }
    })();
    return () => { cancelled = true; };
  }, [api, settings.autoSyncOnLaunch]);

  useEffect(() => {
    const handle = window.setInterval(() => setModelNow(Date.now()), 30000);
    return () => window.clearInterval(handle);
  }, []);

  const saveSettingsState = useCallback(async (next: PwaSettings) => {
    setSettingsState(next);
    await saveSettings(next);
  }, []);

  const saveProfileState = useCallback(async (next: UserProfile) => {
    setProfileState(next);
    await saveProfile(next);
  }, []);

  const openBundle = useCallback(
    async (item: SubstanceSummary) => {
      setStatus(`正在读取 ${displayName(item)}...`);
      setDetailOpen(true);
      setSelectedBundle(null);
      let cached: SubstanceBundle | undefined;
      try {
        cached = await getCachedBundle(item.id);
      } catch (error) {
        console.warn("读取本地详情缓存失败", error);
      }
      if (cached) {
        setSelectedBundle(cached);
        setBundles((current) => ({ ...current, [cached.detail.id]: cached }));
      }
      try {
        const bundle = await api.fetchBundle(item);
        setSelectedBundle(bundle);
        setBundles((current) => ({ ...current, [bundle.detail.id]: bundle }));
        await cacheBundle(bundle);
        setStatus(`已缓存 ${displayName(bundle.detail)} 的详情`);
        return bundle;
      } catch (error) {
        if (!cached) {
          const message = error instanceof Error ? error.message : String(error);
          setStatus(`读取 ${displayName(item)} 失败：${message}`);
          setSelectedBundle({
            detail: { ...item, dataset_version: manifest?.dataset_version },
            interactions: [],
            doseRules: [],
            doseCandidates: [],
            overdoseWarnings: [],
            drugEffects: [],
            pharmacokinetics: [],
            enzymeRelations: [],
            labelSections: [],
            safetyWarnings: [],
            interactionSignals: [],
            foodInteractions: [],
            adverseSignals: [],
            pgx: [],
            fetchedAt: Date.now(),
          });
          throw error;
        }
        setStatus(`使用本地缓存：${displayName(cached.detail)}`);
        return cached;
      }
    },
    [api, manifest?.dataset_version],
  );

  const activeJournal = useMemo(() => activeEntries(journal, bundles, profile, modelNow), [journal, bundles, modelNow, profile]);
  const activeJournalKey = useMemo(
    () => activeJournal.map((entry) => entry.id || `${entry.substanceId}:${entry.timestamp}`).sort().join("|"),
    [activeJournal],
  );
  const activeSignalItems = useMemo(
    () =>
      [...new Map(activeJournal.map((entry) => {
        const detail = bundles[entry.substanceId]?.detail || entry.substanceSnapshot || {
          id: entry.substanceId,
          name_zh: entry.substanceName,
          name_en: entry.substanceName,
        };
        return [detail.id, detail as SubstanceSummary];
      })).values()],
    [activeJournalKey, bundles],
  );

  useEffect(() => {
    let alive = true;
    if (!activeSignalItems.length) {
      setSignalRisks([]);
      return;
    }
    api
      .adverseSignals(activeSignalItems, 3, { liveFallback: settings.liveSignalsEnabled })
      .then((rows) => {
        if (alive) setSignalRisks(adverseSignalRisks(rows, activeJournal));
      })
      .catch(() => {
        if (alive) setSignalRisks([]);
      });
    return () => {
      alive = false;
    };
  }, [activeJournalKey, activeSignalItems, api, settings.liveSignalsEnabled]);

  const computedRisks = useMemo(
    () =>
      sortRisks([
        ...localStaticPairRisks(activeJournal, bundles),
        ...doseRuleRisks(activeJournal, bundles),
        ...overdoseEvidenceRisks(activeJournal, bundles),
        ...modelRisks(activeJournal, bundles, profile),
        ...signalRisks,
      ]),
    [activeJournal, bundles, profile, signalRisks],
  );

  async function addEntry(entry: JournalEntry) {
    await saveJournalEntry(entry);
    setJournal(await allJournal());
    setEntrySheetOpen(false);
    setActiveTab("journal");
  }

  async function deleteEntry(id: string) {
    await deleteJournalEntry(id);
    setJournal(await allJournal());
  }

  const highRiskCount = computedRisks.filter((risk) => riskSortValue(risk.level) >= riskSortValue("Major")).length;

  const tabsWithBadge = useMemo(
    () =>
      tabItems.map((tab) => ({
        ...tab,
        badge: tab.key === "risks" && highRiskCount > 0 ? highRiskCount : undefined,
      })),
    [highRiskCount],
  );

  const handleTabChange = useCallback(
    (key: string) => {
      haptics("light");
      setActiveTab(key as TabKey);
    },
    [haptics],
  );

  const topChrome = (
    <header className="top-chrome">
        <div className="status-pill">
          <Apple size={14} />
          <span>代谢安全</span>
        </div>
        <div className="status-pill subtle">
          <Cloud size={14} />
          <span>{manifest?.dataset_version || "未连接"}</span>
        </div>
    </header>
  );

  const navigationBar = platform.isMobile ? (
    <NavigationBar
      title={tabItems.find((tab) => tab.key === activeTab)?.label || "代谢安全"}
      subtitle={status}
      transparent
      right={
        activeTab === "curve" ? (
          <button
            type="button"
            className="nav-add-button"
            onClick={() => {
              haptics("medium");
              setEntrySheetOpen(true);
            }}
            aria-label="新增摄入"
          >
            <Plus size={22} />
          </button>
        ) : undefined
      }
    />
  ) : null;

  const activeScreen = (
    <>
      <section className="large-title">
        <p>{status}</p>
        <h1>{tabItems.find((tab) => tab.key === activeTab)?.label || "代谢安全"}</h1>
      </section>

      {activeTab === "search" && (
        <SearchPage api={api} manifest={manifest} onOpenBundle={openBundle} selectedBundle={selectedBundle} />
      )}
      {activeTab === "journal" && (
        <JournalPage
          journal={journal}
          onAdd={() => {
            haptics("medium");
            setEntrySheetOpen(true);
          }}
          onDelete={(id) => {
            haptics("warning");
            deleteEntry(id);
          }}
          onClear={async () => {
            haptics("heavy");
            await clearJournal();
            setJournal([]);
          }}
        />
      )}
      {activeTab === "risks" && (
        <RisksPage
          risks={computedRisks}
          activeCount={activeJournal.length}
          onRefresh={() => setStatus("已按当前静态数据库缓存重新计算风险")}
        />
      )}
      {activeTab === "curve" && (
        <CurvePage
          entries={activeJournal}
          bundles={bundles}
          profile={profile}
          risks={computedRisks}
          onAddEntry={() => {
            haptics("medium");
            setEntrySheetOpen(true);
          }}
          onGotoRisks={() => {
            haptics("warning");
            setActiveTab("risks");
          }}
        />
      )}
      {activeTab === "settings" && (
        <SettingsPage
          settings={settings}
          profile={profile}
          journal={journal}
          manifest={manifest}
          bundles={bundles}
          onSaveSettings={saveSettingsState}
          onSaveProfile={saveProfileState}
          onImportTransfer={async ({ profile: importedProfile, journal: importedJournal }) => {
            if (importedProfile) await saveProfileState({ ...defaultProfile, ...importedProfile });
            if (importedJournal?.length) {
              await Promise.all(importedJournal.map((entry) => {
                const snapshot = entry.substanceSnapshot || bundles[entry.substanceId]?.detail;
                return saveJournalEntry({
                  ...entry,
                  id: entry.id || makeId("qr"),
                  substanceName: entry.substanceName || displayName(snapshot) || entry.substanceId,
                  substanceSnapshot: snapshot || entry.substanceSnapshot,
                });
              }));
              const importedBundles: Record<string, SubstanceBundle> = {};
              for (const entry of importedJournal) {
                const snapshot = entry.substanceSnapshot;
                if (snapshot?.id && !bundles[snapshot.id]) {
                  importedBundles[snapshot.id] = {
                    detail: snapshot,
                    interactions: [],
                    doseRules: [],
                    doseCandidates: [],
                    overdoseWarnings: [],
                    drugEffects: [],
                    pharmacokinetics: [],
                    enzymeRelations: [],
                    labelSections: [],
                    safetyWarnings: [],
                    interactionSignals: [],
                    foodInteractions: [],
                    adverseSignals: [],
                    pgx: [],
                    fetchedAt: Date.now(),
                  };
                }
              }
              await Promise.all(Object.values(importedBundles).map(cacheBundle));
              if (Object.keys(importedBundles).length) setBundles((current) => ({ ...current, ...importedBundles }));
              await refreshJournal();
            }
            setStatus(`已导入${importedProfile ? "个人参数" : ""}${importedProfile && importedJournal?.length ? "和" : ""}${importedJournal?.length ? `${importedJournal.length} 条摄入日志` : ""}`);
          }}
          onRefreshJournal={refreshJournal}
          onSetBundles={setBundles}
          onStatus={setStatus}
        />
      )}
    </>
  );

  return (
    <>
      <AdaptiveLayout
        topChrome={!platform.isMobile ? topChrome : undefined}
        navigationBar={navigationBar}
        tabBar={
          platform.isMobile ? (
            <AdaptiveTabBar tabs={tabsWithBadge} activeTab={activeTab} onChange={handleTabChange} hidden={tabBarHidden} />
          ) : undefined
        }
        sidebar={
          !platform.isMobile ? (
            <AdaptiveTabBar tabs={tabsWithBadge} activeTab={activeTab} onChange={handleTabChange} />
          ) : undefined
        }
      >
        {platform.isMobile ? (
          <PullToRefresh onRefresh={async () => refreshJournal()} onScrollDirection={(direction) => setTabBarHidden(direction === "down")}>
            <div style={{ paddingTop: 8 }}>{activeScreen}</div>
          </PullToRefresh>
        ) : (
          activeScreen
        )}
      </AdaptiveLayout>

      <BottomSheet
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        title={selectedBundle ? displayName(selectedBundle.detail) : "读取中"}
        subtitle="详情"
      >
        {!selectedBundle ? <InlineLoading label="读取详情" /> : <SubstanceDetailView bundle={selectedBundle} />}
      </BottomSheet>

      <BottomSheet open={entrySheetOpen} onClose={() => setEntrySheetOpen(false)} title="摄入日志" subtitle="新增">
        <EntrySheetContent api={api} onAdd={addEntry} onBundle={openBundle} onClose={() => setEntrySheetOpen(false)} />
      </BottomSheet>
    </>
  );
}
