/**
 * @module services
 *
 * Service layer barrel export.
 * Domain service façades that coordinate between repositories and business logic.
 */
export { DataPackageManager, COMMON_SHARD_KEYS, type DataPackageStatus, type OfflinePackageInfo, type SyncResult } from "./data-package-manager";
export { JournalService, type JournalSnapshot } from "./journal-service";
export { SubstanceService } from "./substance-service";
export { RiskService, type RiskComputationInput, type RiskComputationResult } from "./risk-service";
export { SettingsService, DEFAULT_SETTINGS } from "./settings-service";
