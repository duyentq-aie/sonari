// The browser's calls to this app's own route handlers. They never throw: a failure comes back
// as a message key, whether the service sent it in its error envelope or the network failed.

import type { ScoreResponse } from "./score";

export type SpeakingItem = { id: string; text: string; unit: string };
export type Result<T> = { ok: true; data: T } | { ok: false; messageKey: string };

export async function call<T>(input: string, init?: RequestInit): Promise<Result<T>> {
  try {
    const response = await fetch(input, init);
    const body: unknown = await response.json().catch(() => null);
    if (response.ok) return { ok: true, data: body as T };
    const key = (body as { error?: { messageKey?: unknown } } | null)?.error?.messageKey;
    return { ok: false, messageKey: typeof key === "string" ? key : "errors.http" };
  } catch {
    return { ok: false, messageKey: "errors.upstream.unavailable" };
  }
}

export function loadItems(): Promise<Result<{ items: SpeakingItem[] }>> {
  return call("/api/speaking-items");
}

/** Sends a recording and the sentence it should say; `data` is the speech service's JSON. */
export async function scoreRecording(
  audio: Blob,
  referenceText: string,
): Promise<Result<ScoreResponse>> {
  const form = new FormData();
  form.append("audio", audio, "recording");
  form.append("referenceText", referenceText);
  const scored = await call<ScoreResponse>("/api/score", { method: "POST", body: form });
  // An answer without words is not a score (an old service, a proxy page): never render it.
  if (scored.ok && !Array.isArray(scored.data?.words)) {
    return { ok: false, messageKey: "errors.internal" };
  }
  return scored;
}
