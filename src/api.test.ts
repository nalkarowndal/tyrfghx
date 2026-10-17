import { describe, expect, it } from "vitest";
import { API_URL } from "./api";
describe("local backend API contract", () => {
  it("uses loopback, never remote by default", () => expect(API_URL).toBe("http://127.0.0.1:8765"));
});
