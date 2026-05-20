/**
 * @module repositories/journal.repository
 *
 * IndexedDB-backed journal repository.
 * Wraps existing db.ts functions behind the JournalRepository interface.
 */
import type { JournalEntry } from "../types";
import { allJournal, saveJournalEntry, deleteJournalEntry, clearJournal } from "../lib/db";
import type { JournalRepository } from "./interfaces";

export class IndexedDBJournalRepository implements JournalRepository {
  async getAll(): Promise<JournalEntry[]> {
    return allJournal();
  }

  async save(entry: JournalEntry): Promise<void> {
    await saveJournalEntry(entry);
  }

  async delete(id: string): Promise<void> {
    await deleteJournalEntry(id);
  }

  async clear(): Promise<void> {
    await clearJournal();
  }
}
