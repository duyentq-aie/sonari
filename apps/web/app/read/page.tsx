"use client";

import { useEffect, useState } from "react";
import { messageFor, t } from "../../lib/messages";
import { loadPassages, READING_UNIT, type Passage } from "../../lib/passages";
import { PassageList } from "./views";

export default function Reading() {
  const [passages, setPassages] = useState<Passage[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadPassages(READING_UNIT).then((loaded) => {
      if (loaded.ok) setPassages(loaded.data.passages);
      else setError(loaded.messageKey);
    });
  }, []);

  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-4 p-4">
      <a className="text-sky-800 underline" href="/">
        {t("reading.toPractice")}
      </a>
      <h1 className="text-2xl font-semibold">{t("reading.heading")}</h1>
      <p>{t("reading.unit")}</p>
      {passages === null && !error && <p>{t("reading.loading")}</p>}
      {passages && <PassageList passages={passages} />}
      {error && (
        <p role="alert" className="rounded-lg bg-red-50 p-3 text-red-800">
          {messageFor(error)}
        </p>
      )}
    </main>
  );
}
