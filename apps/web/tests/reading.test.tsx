import { readFileSync } from "node:fs";
import { join } from "node:path";
import Ajv2020 from "ajv/dist/2020";
import { isValidElement, type ReactElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GET as passageRoute } from "../app/api/passages/[id]/route";
import { GET as passagesRoute } from "../app/api/passages/route";
import Practice from "../app/practice";
import { PassageList, PassageScreen, PassageText } from "../app/read/views";
import { t } from "../lib/messages";
import { passageHref, practiceItems, type Passage, type PassageDetail } from "../lib/passages";

const schema = (name: string) =>
  new Ajv2020().compile(
    JSON.parse(readFileSync(join(import.meta.dirname, "../../../packages/contracts/schema", name), "utf8")),
  );

const ID = "voa:128607@voa-trim/163aae96e072";
const PASSAGE: Passage = { id: ID, title: "Parsley", type: "news_item", url: "https://voa.test/a/128607.html" };
const LIST = { passages: [PASSAGE, { ...PASSAGE, id: "voa:2@voa-trim/x", title: "Second" }] };
const DETAIL: PassageDetail = {
  ...PASSAGE,
  lines: [
    [
      { text: "“Grow it,” she said. ", practicable: false },
      { text: "Parsley is an ancient green.", practicable: true },
    ],
    [{ text: "A plain line with Washington, D.C. in it.", practicable: false }],
    [{ text: "Poor parsley, valued for its looks.", practicable: true }],
  ],
};

/** Every element of a tree that a component returned, without rendering (no DOM here). */
function elements(node: ReactNode): ReactElement<Record<string, unknown>>[] {
  if (Array.isArray(node)) return node.flatMap(elements);
  if (!isValidElement<Record<string, unknown>>(node)) return [];
  return [node, ...elements(node.props.children as ReactNode)];
}

describe("the fixtures", () => {
  it("match the contracts", () => {
    expect(schema("passages-response.schema.json")(LIST)).toBe(true);
    expect(schema("passage-response.schema.json")(DETAIL)).toBe(true);
  });
});

describe("the passage list", () => {
  it("links every passage to its page, with the id encoded", () => {
    const html = renderToStaticMarkup(<PassageList passages={LIST.passages} />);
    expect(html).toContain(">Parsley</a>");
    expect(html).toContain(`href="${passageHref(ID).replace(/&/g, "&amp;")}"`);
    expect(passageHref(ID)).toBe("/read/passage?id=voa%3A128607%40voa-trim%2F163aae96e072");
  });

  it("says so when the unit has no passage", () => {
    expect(renderToStaticMarkup(<PassageList passages={[]} />)).toContain(t("reading.empty"));
  });
});

describe("the passage page", () => {
  it("makes practicable sentences buttons and leaves the rest plain text", () => {
    const html = renderToStaticMarkup(<PassageText passage={DETAIL} onPractise={() => {}} />);
    const buttons = [...html.matchAll(/<button[^>]*>([^<]*)<\/button>/g)].map((m) => m[1]);
    expect(buttons).toEqual(["Parsley is an ancient green.", "Poor parsley, valued for its looks."]);
    expect(html).toContain("<span>A plain line with Washington, D.C. in it.</span>");
    expect(html.match(/<p>/g)).toHaveLength(3);
  });

  it("explains the tappable sentences and credits the source", () => {
    const html = renderToStaticMarkup(
      <PassageScreen passage={DETAIL} practising={null} onPractise={() => {}} onBack={() => {}} />,
    );
    expect(html).toContain(t("reading.hint"));
    expect(html).toContain(`href="${PASSAGE.url}"`);
  });
});

describe("tap to practise", () => {
  it("passes the tapped sentence's place among the practicable ones", () => {
    const onPractise = vi.fn();
    const buttons = elements(PassageText({ passage: DETAIL, onPractise })).filter((e) => e.type === "button");
    (buttons[1].props.onClick as () => void)();
    expect(onPractise).toHaveBeenCalledWith(1);
  });

  it("opens the practice view on the passage's sentences at the one tapped", () => {
    const tree = PassageScreen({ passage: DETAIL, practising: 1, onPractise: () => {}, onBack: () => {} });
    const practice = elements(tree).find((e) => e.type === Practice)!;
    expect(practice.props).toEqual({ given: practiceItems(DETAIL), first: 1 });
    expect(practiceItems(DETAIL)).toEqual([
      { id: `${ID}#0:21`, text: "Parsley is an ancient green.", unit: "Study and work" },
      { id: `${ID}#2:0`, text: "Poor parsley, valued for its looks.", unit: "Study and work" },
    ]);
  });

  it("goes back to the passage", () => {
    const onBack = vi.fn();
    const tree = PassageScreen({ passage: DETAIL, practising: 0, onPractise: () => {}, onBack });
    const back = elements(tree).find((e) => e.type === "button")!;
    expect(back.props.children).toBe(t("reading.back"));
    (back.props.onClick as () => void)();
    expect(onBack).toHaveBeenCalled();
  });

  it("names an item like a speaking item, so a picked sentence finds its listen audio", () => {
    const items = practiceItems({ ...DETAIL, lines: [[{ text: "Poor parsley, valued for its looks, then thrown away.", practicable: true }]] });
    expect(items[0].id).toBe(`${ID}#0:0`);
  });
});

describe("the proxy routes", () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    process.env.CORE_URL = "http://core.test:8000";
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValue(Response.json(LIST));
  });
  afterEach(() => {
    fetchMock.mockReset();
    vi.unstubAllGlobals();
  });

  it("asks the core service for a unit's passages and passes nothing else on", async () => {
    const response = await passagesRoute(new Request("http://web.test/api/passages?unit=Study and work&x=1"));
    expect(fetchMock.mock.calls[0][0]).toBe("http://core.test:8000/v1/passages?unit=Study%20and%20work");
    expect(await response.json()).toEqual(LIST);
  });

  it("forwards one passage's id as one encoded segment", async () => {
    await passageRoute(new Request(`http://web.test/api/passages/${encodeURIComponent(ID)}`));
    expect(fetchMock.mock.calls[0][0]).toBe(`http://core.test:8000/v1/passages/${encodeURIComponent(ID)}`);
  });

  it("refuses an id that is not valid percent-encoding, without calling the service", async () => {
    const response = await passageRoute(new Request("http://web.test/api/passages/%E0%A4%A"));
    expect(response.status).toBe(422);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
