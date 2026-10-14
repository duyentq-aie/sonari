import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Listen } from "../app/listen";
import { listenSources, VOICES } from "../lib/listen";
import { hasMessage, t } from "../lib/messages";
import manifest from "../public/listen/manifest.json";

const PUBLIC = join(import.meta.dirname, "../public");
const ITEMS = readFileSync(
  join(import.meta.dirname, "../../../tools/speaking_items/items.jsonl"),
  "utf8",
)
  .split("\n")
  .filter(Boolean)
  .map((line) => JSON.parse(line) as { source: string; line: number; start: number });
const IDS = ITEMS.map((item) => `${item.source}#${item.line}:${item.start}`);

describe("listen audio", () => {
  it("has a file in both voices for every practice sentence, and every file is served", () => {
    expect(IDS).toHaveLength(20);
    for (const id of IDS) {
      const sources = listenSources(id);
      expect(Object.keys(sources).sort(), id).toEqual([...VOICES].sort());
      for (const src of Object.values(sources)) expect(existsSync(join(PUBLIC, src!)), src).toBe(true);
    }
    expect(Object.keys(manifest.voices).sort()).toEqual([...VOICES].sort());
  });

  it("offers both voices, American first, and plays the chosen one", () => {
    const html = renderToStaticMarkup(<Listen itemId={IDS[0]} />);
    expect(html).toContain(t("practice.listen.play"));
    expect(html).toContain(t("practice.listen.synthetic"));
    const pressed = [...html.matchAll(/aria-pressed="(\w+)">([^<]+)</g)].map((m) => [m[2], m[1]]);
    expect(pressed).toEqual([
      [t("practice.listen.voices.us"), "true"],
      [t("practice.listen.voices.gb"), "false"],
    ]);
    expect(html).toContain(`src="${listenSources(IDS[0]).us}"`);
    const british = renderToStaticMarkup(<Listen itemId={IDS[0]} initial="gb" />);
    expect(british).toContain(`src="${listenSources(IDS[0]).gb}"`);
  });

  it("shows nothing for an item without audio", () => {
    expect(renderToStaticMarkup(<Listen itemId="voa:0@x#0:0" />)).toBe("");
  });

  it("has copy for each voice", () => {
    for (const voice of VOICES) expect(hasMessage(`practice.listen.voices.${voice}`)).toBe(true);
  });
});
