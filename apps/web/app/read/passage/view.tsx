"use client";

import { useEffect, useState } from "react";
import { messageFor, t } from "../../../lib/messages";
import { loadPassage, type PassageDetail } from "../../../lib/passages";
import { PassageScreen } from "../views";

export default function PassageView({ id }: { id: string }) {
  const [passage, setPassage] = useState<PassageDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [practising, setPractising] = useState<number | null>(null);

  useEffect(() => {
    loadPassage(id).then((loaded) => {
      if (loaded.ok) setPassage(loaded.data);
      else setError(loaded.messageKey);
    });
  }, [id]);

  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-4 p-4">
      <a className="text-sky-800 underline" href="/read">
        {t("reading.toList")}
      </a>
      {!passage && !error && <p>{t("reading.loading")}</p>}
      {passage && (
        <PassageScreen
          passage={passage}
          practising={practising}
          onPractise={setPractising}
          onBack={() => setPractising(null)}
        />
      )}
      {error && (
        <p role="alert" className="rounded-lg bg-red-50 p-3 text-red-800">
          {messageFor(error)}
        </p>
      )}
    </main>
  );
}
