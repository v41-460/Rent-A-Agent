import { describe, expect, it } from "vitest";
import { safeNext } from "@/components/AuthForm";
import { iconText } from "@/lib/icon";

describe("safeNext", () => {
  it("allows pages on this site", () => expect(safeNext("/agents/bills")).toBe("/agents/bills"));
  it("blocks other sites", () => {
    expect(safeNext("https://evil.example")).toBe("/");
    expect(safeNext("//evil.example")).toBe("/");
    expect(safeNext(null)).toBe("/");
  });
});

describe("iconText", () => {
  it("keeps emoji", () => expect(iconText("🧾")).toBe("🧾"));
  it("falls back for file icons", () => expect(iconText("icon.svg")).toBe("🤖"));
});
