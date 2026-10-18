import type { GenerationPreview } from "./nativeGenerationGallery";

export type ImageZoom = 50 | 100 | 200;
export const IMAGE_ZOOMS = [50, 100, 200] as const;

/** A disappearing/invalid selected ID cannot open an arbitrary local image. */
export function selectPreview(
  items: readonly GenerationPreview[], selectedId: string | null,
): GenerationPreview | null {
  return selectedId ? items.find(item => item.id === selectedId) ?? null : null;
}

/** Stable, bounded gallery navigation; only preverified incoming previews. */
export function adjacentPreviewId(
  items: readonly GenerationPreview[], currentId: string, direction: -1 | 1,
): string | null {
  if (items.length === 0) return null;
  const index = items.findIndex(item => item.id === currentId);
  if (index < 0) return null;
  const target = index + direction;
  return target >= 0 && target < items.length ? items[target].id : null;
}

/** No arbitrary dynamic zoom or image style string crosses this boundary. */
export function adjustImageZoom(current: ImageZoom, direction: -1 | 1): ImageZoom {
  const index = IMAGE_ZOOMS.indexOf(current);
  const next = Math.max(0, Math.min(IMAGE_ZOOMS.length - 1, index + direction));
  return IMAGE_ZOOMS[next];
}

export function imageDimensionLabel(image: Pick<GenerationPreview, "width" | "height">): string {
  if (![image.width, image.height].every(v => Number.isSafeInteger(v) && v >= 1 && v <= 1024)) {
    return "해상도 확인 불가";
  }
  return `${image.width}×${image.height}`;
}
