import { describe, expect, it } from "vitest";
import { adjacentPreviewId, adjustImageZoom, imageDimensionLabel, selectPreview } from "./generationGalleryView";
import type { GenerationPreview } from "./nativeGenerationGallery";

const gallery: GenerationPreview[] = ["a", "b", "c"].map(letter => ({
  id: `aiimage-${letter.repeat(32)}.png`,
  image_src: "data:image/png;base64,cG5n",
  size_bytes: 2048, width: 512, height: 768,
}));

describe("M3-21 verified-image gallery inspection helpers", () => {
  it("never resolves images missing from the current verified gallery", () => {
    expect(selectPreview(gallery, null)).toBeNull();
    expect(selectPreview(gallery, "../../private.png")).toBeNull();
    expect(selectPreview(gallery, gallery[1].id)).toBe(gallery[1]);
    expect(selectPreview([], gallery[1].id)).toBeNull();
  });
  it("navigates only to existing adjacent preview IDs and respects bounds", () => {
    expect(adjacentPreviewId(gallery, gallery[1].id, -1)).toBe(gallery[0].id);
    expect(adjacentPreviewId(gallery, gallery[1].id, 1)).toBe(gallery[2].id);
    expect(adjacentPreviewId(gallery, gallery[0].id, -1)).toBeNull();
    expect(adjacentPreviewId(gallery, gallery[2].id, 1)).toBeNull();
    expect(adjacentPreviewId(gallery, "unknown", 1)).toBeNull();
    expect(adjacentPreviewId([], gallery[0].id, 1)).toBeNull();
  });
  it("only supports 50, 100 and 200 percent zoom", () => {
    expect(adjustImageZoom(50, -1)).toBe(50);
    expect(adjustImageZoom(50, 1)).toBe(100);
    expect(adjustImageZoom(100, 1)).toBe(200);
    expect(adjustImageZoom(200, 1)).toBe(200);
    expect(adjustImageZoom(200, -1)).toBe(100);
  });
  it("labels actual bounded native-decoded image dimensions", () => {
    expect(imageDimensionLabel(gallery[0])).toBe("512×768");
    expect(imageDimensionLabel({ width: 0, height: 1024 })).toBe("해상도 확인 불가");
    expect(imageDimensionLabel({ width: 1024, height: 1025 })).toBe("해상도 확인 불가");
    expect(imageDimensionLabel({ width: NaN, height: 400 })).toBe("해상도 확인 불가");
  });
});
