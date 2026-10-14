// The "listen" audio: static files made offline by Kokoro-82M (tools/listen_audio), one per
// speaking item and voice. No speech is synthesised at runtime.
import manifest from "../public/listen/manifest.json";

export type Voice = "us" | "gb";
export const VOICES: readonly Voice[] = ["us", "gb"];

/** The URL of each voice's audio for an item; an item with none gets no listen control. */
export function listenSources(itemId: string): Partial<Record<Voice, string>> {
  const found: Partial<Record<Voice, string>> = {};
  for (const entry of manifest.files) {
    if (entry.item === itemId) found[entry.voice as Voice] = `/listen/${entry.file}`;
  }
  return found;
}
