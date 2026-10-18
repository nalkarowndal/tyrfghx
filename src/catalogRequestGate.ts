/**
 * An IPC response is UI-authoritative only if BOTH the catalog snapshot and
 * the specific user request still match. It is safe for native calls to finish
 * after navigation or a refresh; their late result must simply be discarded.
 */
export function belongsToActiveCatalogRequest(
  launchedCatalogEpoch: number,
  launchedRequestId: number,
  currentCatalogEpoch: number,
  currentRequestId: number,
): boolean {
  return launchedCatalogEpoch === currentCatalogEpoch
    && launchedRequestId === currentRequestId;
}
