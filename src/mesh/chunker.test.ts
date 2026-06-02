import { describe, expect, it } from "vitest";
import { byteLength, chunkForMesh } from "./chunker.js";

describe("chunkForMesh", () => {
  it("returns a single chunk for short ASCII", () => {
    const chunks = chunkForMesh("hello world");
    expect(chunks).toEqual(["[1/1] hello world"]);
  });

  it("returns a single chunk for empty string", () => {
    const chunks = chunkForMesh("");
    expect(chunks).toEqual(["[1/1] "]);
  });

  it("splits long ASCII into multiple chunks within byte budget", () => {
    const long = "a".repeat(1000);
    const chunks = chunkForMesh(long);
    expect(chunks.length).toBeGreaterThan(1);
    for (const c of chunks) {
      expect(byteLength(c)).toBeLessThanOrEqual(200);
    }
    expect(chunks.map(stripHeader).join("")).toBe(long);
  });

  it("respects custom byte budget", () => {
    const chunks = chunkForMesh("a".repeat(120), { maxBytes: 50 });
    for (const c of chunks) {
      expect(byteLength(c)).toBeLessThanOrEqual(50);
    }
  });

  it("never splits a multi-byte UTF-8 codepoint (Chinese)", () => {
    const zh = "野外求生".repeat(40);
    const chunks = chunkForMesh(zh, { maxBytes: 60 });
    for (const c of chunks) {
      expect(byteLength(c)).toBeLessThanOrEqual(60);
      expect(c).not.toContain("�");
    }
    expect(chunks.map(stripHeader).join("")).toBe(zh);
  });

  it("never splits a 4-byte emoji codepoint", () => {
    const emoji = "🏕️🐍🍄🩹".repeat(30);
    const chunks = chunkForMesh(emoji, { maxBytes: 40 });
    for (const c of chunks) {
      expect(byteLength(c)).toBeLessThanOrEqual(40);
      expect(c).not.toContain("�");
    }
    expect(chunks.map(stripHeader).join("")).toBe(emoji);
  });

  it("numbers chunks consistently (i/n)", () => {
    const chunks = chunkForMesh("x".repeat(800));
    const n = chunks.length;
    chunks.forEach((c, i) => {
      expect(c.startsWith(`[${i + 1}/${n}] `)).toBe(true);
    });
  });

  it("throws when maxBytes is not big enough for a header", () => {
    expect(() => chunkForMesh("hi", { maxBytes: 4 })).toThrow();
  });
});

function stripHeader(chunk: string): string {
  return chunk.replace(/^\[\d+\/\d+\]\s/, "");
}
