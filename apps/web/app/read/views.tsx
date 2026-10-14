// The reading pages without state, so tests can render them: the list, the passage, and the switch
// from the passage to the practice view of a tapped sentence.
import { t } from "../../lib/messages";
import { passageHref, practiceItems, type Passage, type PassageDetail } from "../../lib/passages";
import Practice from "../practice";
import { CARD } from "../result";

const LINK = "text-sky-800 underline";
// A sentence that can be practised: a visible, tappable target. The rest is plain text.
const SENTENCE =
  "inline rounded bg-sky-50 text-left underline box-decoration-clone decoration-sky-400 decoration-2 underline-offset-4 hover:bg-sky-100";

export function PassageList({ passages }: { passages: Passage[] }) {
  if (passages.length === 0) return <p>{t("reading.empty")}</p>;
  return (
    <ul className="flex flex-col gap-2">
      {passages.map((passage) => (
        <li key={passage.id} className={CARD}>
          <a lang="en" className={LINK} href={passageHref(passage.id)}>
            {passage.title}
          </a>
        </li>
      ))}
    </ul>
  );
}

export function PassageText({ passage, onPractise }: { passage: PassageDetail; onPractise: (index: number) => void }) {
  let next = 0; // the practice index of the next practicable sentence, in reading order
  return (
    <article lang="en" className={`${CARD} flex flex-col gap-3`}>
      <h2 className="text-xl font-semibold">{passage.title}</h2>
      {passage.lines.map((line, number) => (
        <p key={number}>
          {line.map((segment, at) => {
            if (!segment.practicable) return <span key={at}>{segment.text}</span>;
            const index = next++;
            return (
              <button key={at} className={SENTENCE} onClick={() => onPractise(index)}>
                {segment.text}
              </button>
            );
          })}
        </p>
      ))}
    </article>
  );
}

type Screen = { passage: PassageDetail; practising: number | null; onPractise: (index: number) => void; onBack: () => void };

/** The passage, or the practice view of its sentences opened at the one tapped. */
export function PassageScreen({ passage, practising, onPractise, onBack }: Screen) {
  if (practising !== null) {
    return (
      <div className="flex flex-col gap-2">
        <button className={`${LINK} self-start px-4`} onClick={onBack}>
          {t("reading.back")}
        </button>
        <Practice given={practiceItems(passage)} first={practising} />
      </div>
    );
  }
  return (
    <>
      <p>{t("reading.hint")}</p>
      <PassageText passage={passage} onPractise={onPractise} />
      <p className="text-sm text-slate-600">
        {t("reading.source")}{" "}
        <a className={LINK} href={passage.url} rel="noopener noreferrer" target="_blank">
          VOA Learning English
        </a>
      </p>
    </>
  );
}
