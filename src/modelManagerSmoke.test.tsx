import { afterEach, describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { isTauri } from "@tauri-apps/api/core";
import type { ModelRecord } from "./api";
import ModelLibrary from "./ModelLibrary";

vi.mock("@tauri-apps/api/core", () => ({
  isTauri: vi.fn(),
  invoke: vi.fn(),
}));
afterEach(() => vi.resetAllMocks());

function model(
  id: string, category: ModelRecord["category"], file_format: ModelRecord["file_format"],
): ModelRecord {
  return {
    id, name: id.split("/")[1], category, file_format,
    size_bytes: 1024, validation: file_format === "ckpt" ? "blocked_legacy" : "metadata_only",
    reported_architecture: null, note: "Metadata only", display_name: null,
    family: null, family_source: "unknown", license: null, notes: null,
    integrity_state: "not_recorded", recorded_sha256: null,
    potential_duplicate_ids: [],
  };
}

const fixtures = [
  model("checkpoints/base.safetensors", "checkpoint", "safetensors"),
  model("loras/style.safetensors", "lora", "safetensors"),
  model("vae/legacy.ckpt", "vae", "ckpt"),
];

describe("M3-25 model manager render smoke", () => {
  it("shows two explicit native SHA-256 actions for safetensors in Tauri only", () => {
    vi.mocked(isTauri).mockReturnValue(true);
    const html = renderToStaticMarkup(
      <ModelLibrary items={fixtures} isLoading={false} error="" onRefresh={() => {}} />,
    );
    expect(html.match(/현재 파일 SHA-256 검증/g)).toHaveLength(2);
    expect(html).toContain("로컬 모델 관리");
    expect(html).toContain("legacy.ckpt");
    expect(html).toContain("CKPT 자동 로딩"); // ModelLibrary labels are conservative.
    expect(html).not.toContain("이미지 생성 완료");
  });

  it("never exposes a native rehash action on a browser-only page", () => {
    vi.mocked(isTauri).mockReturnValue(false);
    const html = renderToStaticMarkup(
      <ModelLibrary items={fixtures} isLoading={false} error="" onRefresh={() => {}} />,
    );
    expect(html).not.toContain("현재 파일 SHA-256 검증");
    expect(html).toContain("브라우저에서는 파일 가져오기 버튼을 사용할 수 없습니다.");
  });

  it("renders an error without treating it as a successful verification", () => {
    vi.mocked(isTauri).mockReturnValue(true);
    const html = renderToStaticMarkup(
      <ModelLibrary items={[]} isLoading={false} error="모델 목록 실패" onRefresh={() => {}} />,
    );
    expect(html).toContain("모델 목록 오류");
    expect(html).toContain("모델 목록 실패");
    expect(html).not.toContain("일치합니다 (검사 시점 기준)");
  });
});
