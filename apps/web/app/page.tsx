import { t } from "../lib/messages";
import Practice from "./practice";

export default function Page() {
  return (
    <>
      <Practice />
      <p className="mx-auto max-w-2xl px-4 pb-4">
        <a className="text-sky-800 underline" href="/read">
          {t("reading.open")}
        </a>
      </p>
    </>
  );
}
