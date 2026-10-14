"use client";

import { useEffect, useRef, useState } from "react";
import { loadItems, scoreRecording, type SpeakingItem } from "../lib/api";
import { messageFor, t } from "../lib/messages";
import { RecorderError, startRecording, type Recording } from "../lib/recorder";
import { isDebug, step, type ScoreResponse } from "../lib/score";
import { Listen } from "./listen";
import { CARD, ScoreView } from "./result";

type Phase = "loading" | "idle" | "recording" | "scoring";

const button =
  "rounded-lg px-4 py-2 font-medium text-white disabled:opacity-40 bg-slate-800 hover:bg-slate-700";

/** The practice view. Without `items` it practises the speaking items; a reading page passes the
 *  sentences of a passage and the one tapped (`first`). */
export default function Practice({ given, first = 0 }: { given?: SpeakingItem[]; first?: number }) {
  const [items, setItems] = useState<SpeakingItem[]>(given ?? []);
  const [index, setIndex] = useState(first);
  const [phase, setPhase] = useState<Phase>("loading");
  const [error, setError] = useState<string | null>(null); // a message key
  const [audio, setAudio] = useState<Blob | null>(null); // kept so a failed scoring can be resent
  const [result, setResult] = useState<ScoreResponse | null>(null);
  const [selected, setSelected] = useState<number | null>(null); // the word whose phonemes show
  const [debug, setDebug] = useState(false);
  const recording = useRef<Recording | null>(null);
  const item = items[index];

  useEffect(() => {
    setDebug(isDebug(window.location.search));
    if (given) {
      setPhase("idle");
    } else {
      loadItems().then((loaded) => {
        if (loaded.ok) setItems(loaded.data.items);
        else setError(loaded.messageKey);
        setPhase("idle");
      });
    }
    return () => void recording.current?.stop(); // leaving the page must release the microphone
  }, []);

  function clear() {
    setResult(null);
    setSelected(null);
    setError(null);
    setAudio(null);
  }

  async function submit(blob: Blob) {
    setPhase("scoring");
    setError(null);
    const scored = await scoreRecording(blob, item.text);
    if (scored.ok) setResult(scored.data);
    else setError(scored.messageKey);
    setPhase("idle");
  }

  async function start() {
    clear();
    try {
      recording.current = await startRecording();
      setPhase("recording");
    } catch (problem) {
      setError(`errors.mic.${problem instanceof RecorderError ? problem.problem : "unavailable"}`);
    }
  }

  async function stop() {
    const blob = await recording.current!.stop();
    recording.current = null;
    setAudio(blob);
    await submit(blob);
  }

  function go(delta: number) {
    setIndex(step(index, delta, items.length));
    clear();
  }

  const busy = phase !== "idle";
  const canMove = !busy && items.length > 1;
  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-4 p-4">
      <h1 className="text-2xl font-semibold">{t("practice.heading")}</h1>
      <p>{t("practice.instruction")}</p>
      <p className="text-sm text-slate-600">{t("practice.notice")}</p>

      {phase === "loading" && <p>{t("practice.loading")}</p>}
      {phase !== "loading" && !item && !error && <p>{t("practice.empty")}</p>}
      {item && (
        <nav className="flex items-center justify-between gap-2">
          <button className={button} onClick={() => go(-1)} disabled={!canMove}>
            {t("practice.previous")}
          </button>
          <span>{t("practice.position", { n: index + 1, total: items.length })}</span>
          <button className={button} onClick={() => go(1)} disabled={!canMove}>
            {t("practice.next")}
          </button>
        </nav>
      )}
      {item && !result && (
        <p lang="en" className={CARD}>
          {item.text}
        </p>
      )}
      {result && <ScoreView result={result} selected={selected} onSelect={setSelected} />}
      {item && <Listen itemId={item.id} />}

      <div className="flex flex-wrap gap-2">
        {phase === "recording" ? (
          <button className={button} onClick={stop}>
            {t("practice.stop")}
          </button>
        ) : (
          <button className={button} onClick={start} disabled={busy || !item}>
            {audio || result ? t("practice.again") : t("practice.record")}
          </button>
        )}
        {error && audio && (
          <button className={button} onClick={() => submit(audio)} disabled={busy}>
            {t("practice.retry")}
          </button>
        )}
      </div>

      {phase === "recording" && <p role="status">{t("practice.recording")}</p>}
      {phase === "scoring" && <p role="status">{t("practice.scoring")}</p>}
      {error && (
        <p role="alert" className="rounded-lg bg-red-50 p-3 text-red-800">
          {messageFor(error)}
        </p>
      )}
      {debug && result && (
        <section>
          <h2 className="font-medium">{t("practice.result")}</h2>
          <pre className="overflow-x-auto rounded-lg bg-slate-900 p-3 text-sm text-slate-100">
            {JSON.stringify(result, null, 2)}
          </pre>
        </section>
      )}
    </main>
  );
}
