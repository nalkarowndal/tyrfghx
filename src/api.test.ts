import { afterEach, describe, expect, it, vi } from "vitest";
import { API_URL, getCompatibility } from "./api";
describe("local backend API contract", () => {
  it("uses loopback, never remote by default", () => expect(API_URL).toBe("http://127.0.0.1:8765"));
});

afterEach(() => vi.unstubAllGlobals());
it("encodes model identifiers for read-only compatibility requests", async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ status: "unknown", checkpoint_id: "checkpoints/A B.safetensors", lora_id: "loras/L.safetensors", summary: "Unknown" }),
  });
  vi.stubGlobal("fetch", fetchMock);
  const result = await getCompatibility("checkpoints/A B.safetensors", "loras/L.safetensors");
  const url = new URL(fetchMock.mock.calls[0][0] as string);
  expect(url.pathname).toBe("/api/models/compatibility");
  expect(url.searchParams.get("checkpoint_id")).toBe("checkpoints/A B.safetensors");
  expect(url.searchParams.get("lora_id")).toBe("loras/L.safetensors");
  expect(result.status).toBe("unknown");
});
