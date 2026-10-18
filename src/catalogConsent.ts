import type { ModelRecord } from "./api";

/**
 * Permission is a point-in-time decision tied to the exact catalog snapshot.
 * Matching model IDs are insufficient: files can be replaced between refreshes.
 * The caller must still pass the GPU preflight and backend's native safety gates.
 */
export function hasCurrentCatalogConsent(
  consentedCatalog: readonly ModelRecord[] | null,
  currentCatalog: readonly ModelRecord[],
  isLoading: boolean,
  error: string,
): boolean {
  return consentedCatalog !== null
    && consentedCatalog === currentCatalog
    && currentCatalog.length > 0
    && !isLoading
    && !error;
}
