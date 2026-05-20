/**
 * @module services/journal-service
 *
 * Domain service façade for journal operations.
 * Coordinates between the journal repository and risk/exposure computation.
 */
import type { JournalEntry, SubstanceBundle, UserProfile } from "../types";
import type { JournalRepository } from "../repositories/interfaces";
import { activeEntries } from "../lib/pk";

// ── Types ─────────────────────────────────────────────────────────────

export interface JournalSnapshot {
  entries: JournalEntry[];
  activeEntries: JournalEntry[];
  activeSubstanceIds: string[];
  totalCount: number;
  activeCount: number;
}

// ── JournalService ────────────────────────────────────────────────────

export class JournalService {
  private readonly repo: JournalRepository;

  constructor(repo: JournalRepository) {
    this.repo = repo;
  }

  /**
   * Returns all journal entries.
   */
  async getAll(): Promise<JournalEntry[]> {
    return this.repo.getAll();
  }

  /**
   * Saves a journal entry.
   */
  async save(entry: JournalEntry): Promise<void> {
    await this.repo.save(entry);
  }

  /**
   * Deletes a journal entry by id.
   */
  async delete(id: string): Promise<void> {
    await this.repo.delete(id);
  }

  /**
   * Clears all journal entries.
   */
  async clear(): Promise<void> {
    await this.repo.clear();
  }

  /**
   * Returns a snapshot of the journal with active entries filtered by PK model.
   */
  async getSnapshot(
    bundles: Record<string, SubstanceBundle>,
    profile: UserProfile,
    now = Date.now(),
  ): Promise<JournalSnapshot> {
    const entries = await this.repo.getAll();
    const active = activeEntries(entries, bundles, profile, now);
    const activeSubstanceIds = [...new Set(active.map((e) => e.substanceId).filter(Boolean))];

    return {
      entries,
      activeEntries: active,
      activeSubstanceIds,
      totalCount: entries.length,
      activeCount: active.length,
    };
  }

  /**
   * Builds unique substance items from active journal entries for signal queries.
   * Returns a list of SubstanceSummary-compatible objects.
   */
  buildSignalItems(
    activeJournal: JournalEntry[],
    bundles: Record<string, SubstanceBundle>,
  ): Array<{ id: string; name_en?: string; name_zh?: string; aliases?: string[] }> {
    const byId = new Map<string, { id: string; name_en?: string; name_zh?: string; aliases?: string[] }>();
    for (const entry of activeJournal) {
      const detail = bundles[entry.substanceId]?.detail || entry.substanceSnapshot || {
        id: entry.substanceId,
        name_zh: entry.substanceName,
        name_en: entry.substanceName,
      };
      if (detail.id && !byId.has(detail.id)) {
        byId.set(detail.id, detail as { id: string; name_en?: string; name_zh?: string; aliases?: string[] });
      }
    }
    return [...byId.values()];
  }
}
