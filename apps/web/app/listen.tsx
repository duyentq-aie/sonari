"use client";

import { useRef, useState } from "react";
import { listenSources, VOICES, type Voice } from "../lib/listen";
import { t } from "../lib/messages";

const choice = "rounded-lg border px-3 py-1 text-sm aria-pressed:bg-slate-800 aria-pressed:text-white";

/** Plays the item's sentence read by a synthetic voice, American or British. */
export function Listen({ itemId, initial = "us" }: { itemId: string; initial?: Voice }) {
  const [voice, setVoice] = useState<Voice>(initial);
  const audio = useRef<HTMLAudioElement>(null);
  const sources = listenSources(itemId);
  const voices = VOICES.filter((v) => sources[v]);
  if (voices.length === 0) return null;
  const chosen = sources[voice] ? voice : voices[0];

  function play() {
    const element = audio.current;
    if (!element) return;
    element.currentTime = 0;
    element.play().catch(() => {}); // a refused play leaves the page as it was
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button className="rounded-lg bg-sky-700 px-4 py-2 font-medium text-white" onClick={play}>
        {t("practice.listen.play")}
      </button>
      <span className="text-sm">{t("practice.listen.voice")}</span>
      {voices.map((v) => (
        <button key={v} className={choice} aria-pressed={v === chosen} onClick={() => setVoice(v)}>
          {t(`practice.listen.voices.${v}`)}
        </button>
      ))}
      <audio ref={audio} preload="none" src={sources[chosen]} data-voice={chosen} />
      <p className="w-full text-sm text-slate-600">{t("practice.listen.synthetic")}</p>
    </div>
  );
}
