// The reading pages' data: GET /v1/passages and GET /v1/passages/{id} on the core service
// (packages/contracts/schema/passage*-response.schema.json), through this app's route handlers.
import { call, type Result, type SpeakingItem } from "./api";

export const READING_UNIT = "Study and work"; // the API's unit name, never shown

export type Passage = { id: string; title: string; type: "explainer" | "news_item"; url: string };
export type Segment = { text: string; practicable: boolean };
export type PassageDetail = Passage & { lines: Segment[][] };

export function loadPassages(unit: string): Promise<Result<{ passages: Passage[] }>> {
  return call(`/api/passages?unit=${encodeURIComponent(unit)}`);
}

export function loadPassage(id: string): Promise<Result<PassageDetail>> {
  return call(`/api/passages/${encodeURIComponent(id)}`);
}

/** The page of one passage; its id holds "/" and ":", so it travels as a query parameter. */
export function passageHref(id: string): string {
  return `/read/passage?id=${encodeURIComponent(id)}`;
}

/** The passage's practicable sentences as practice items, in reading order. An item's id is the
 *  speaking items' key (source#line:start, offsets in code points), so a sentence that is also a
 *  speaking item finds its listen audio. */
export function practiceItems(passage: PassageDetail): SpeakingItem[] {
  return passage.lines.flatMap((line, number) => {
    let at = 0;
    return line.flatMap((segment) => {
      const start = at;
      at += Array.from(segment.text).length;
      if (!segment.practicable) return [];
      return [{ id: `${passage.id}#${number}:${start}`, text: segment.text, unit: READING_UNIT }];
    });
  });
}
