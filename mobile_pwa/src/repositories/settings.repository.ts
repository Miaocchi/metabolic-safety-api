/**
 * @module repositories/settings.repository
 *
 * IndexedDB-backed settings repository.
 * Wraps existing db.ts functions behind the SettingsRepository interface.
 */
import type { PwaSettings, UserProfile } from "../types";
import { loadProfile, saveProfile, loadSettings, saveSettings } from "../lib/db";
import type { SettingsRepository } from "./interfaces";

export class IndexedDBSettingsRepository implements SettingsRepository {
  async loadProfile(): Promise<UserProfile | undefined> {
    return loadProfile();
  }

  async saveProfile(profile: UserProfile): Promise<void> {
    await saveProfile(profile);
  }

  async loadSettings(): Promise<PwaSettings | undefined> {
    return loadSettings();
  }

  async saveSettings(settings: PwaSettings): Promise<void> {
    await saveSettings(settings);
  }
}
