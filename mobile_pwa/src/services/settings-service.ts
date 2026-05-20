/**
 * @module services/settings-service
 *
 * Domain service façade for user settings and profile management.
 */
import type { PwaSettings, UserProfile } from "../types";
import type { SettingsRepository } from "../repositories/interfaces";
import { defaultProfile } from "../lib/pk";

// ── Constants ─────────────────────────────────────────────────────────

export const DEFAULT_SETTINGS: PwaSettings = {
  apiBase: "https://miaocchi.github.io/metabolic-safety-api/api",
  localApiBase: "/local-api",
  cacheMode: "recent",
  localBackendEnabled: false,
  remoteProvider: "github",
  staticDbMode: "local-first",
  liveSignalsEnabled: false,
  autoSyncOnLaunch: true,
};

const BUILTIN_API = "https://miaocchi.github.io/metabolic-safety-api/api";

// ── SettingsService ───────────────────────────────────────────────────

export class SettingsService {
  private readonly repo: SettingsRepository;
  private currentSettings: PwaSettings;
  private currentProfile: UserProfile;

  constructor(repo: SettingsRepository) {
    this.repo = repo;
    this.currentSettings = { ...DEFAULT_SETTINGS };
    this.currentProfile = { ...defaultProfile };
  }

  /**
   * Initializes settings from persisted storage.
   * Returns the loaded settings and profile with defaults merged.
   */
  async initialize(): Promise<{ settings: PwaSettings; profile: UserProfile }> {
    const [storedSettings, storedProfile] = await Promise.all([
      this.repo.loadSettings().catch(() => undefined),
      this.repo.loadProfile().catch(() => undefined),
    ]);

    if (storedSettings) {
      const apiBase = storedSettings.apiBase || DEFAULT_SETTINGS.apiBase;
      this.currentSettings = {
        ...DEFAULT_SETTINGS,
        ...storedSettings,
        apiBase,
        localBackendEnabled: false,
        staticDbMode: storedSettings.staticDbMode || "local-first",
      };
    }

    if (storedProfile) {
      this.currentProfile = { ...defaultProfile, ...storedProfile };
    }

    return { settings: this.currentSettings, profile: this.currentProfile };
  }

  /**
   * Returns the current settings.
   */
  getSettings(): PwaSettings {
    return this.currentSettings;
  }

  /**
   * Returns the current profile.
   */
  getProfile(): UserProfile {
    return this.currentProfile;
  }

  /**
   * Returns the builtin API base URL.
   */
  getBuiltinApiBase(): string {
    return BUILTIN_API;
  }

  /**
   * Returns the effective API base URL.
   */
  getEffectiveApiBase(): string {
    return this.currentSettings.apiBase || BUILTIN_API;
  }

  /**
   * Saves and applies new settings.
   */
  async saveSettings(next: PwaSettings): Promise<void> {
    this.currentSettings = next;
    await this.repo.saveSettings(next);
  }

  /**
   * Saves and applies a new profile.
   */
  async saveProfile(next: UserProfile): Promise<void> {
    this.currentProfile = next;
    await this.repo.saveProfile(next);
  }

  /**
   * Updates the remote API base URL.
   */
  async updateRemoteApiBase(apiBase: string, provider: PwaSettings["remoteProvider"]): Promise<void> {
    const trimmed = apiBase.trim().replace(/\/+$/, "");
    await this.saveSettings({
      ...this.currentSettings,
      remoteProvider: provider,
      apiBase: trimmed || BUILTIN_API,
      localBackendEnabled: false,
      staticDbMode: "local-first",
    });
  }
}
