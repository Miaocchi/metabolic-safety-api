import { beforeEach, describe, expect, it } from "vitest";
import { allJournal, clearJournal, saveJournalEntry, saveProfile, loadProfile } from "./db";
import { defaultProfile } from "./pk";

describe("IndexedDB repository", () => {
  beforeEach(async () => {
    await clearJournal().catch(() => undefined);
  });

  it("persists journal entries", async () => {
    await saveJournalEntry({
      id: "entry-test",
      substanceId: "ibuprofen",
      substanceName: "Ibuprofen",
      timestamp: 1000,
      dosage: 200,
      unit: "mg",
      route: "Oral",
      stomachState: "Light",
    });
    const rows = await allJournal();
    expect(rows).toHaveLength(1);
    expect(rows[0].substanceId).toBe("ibuprofen");
  });

  it("persists profile settings", async () => {
    await saveProfile({ ...defaultProfile, weightKg: 88 });
    await expect(loadProfile()).resolves.toMatchObject({ weightKg: 88 });
  });
});
