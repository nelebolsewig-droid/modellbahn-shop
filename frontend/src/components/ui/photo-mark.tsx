import { Wordmark } from "@/components/site/wordmark";
import { cn } from "@/lib/utils";

/** The names of the finishes as the shop says them; an unknown code is shown as it is. */
const FINISH_NAMES: Record<string, string> = {
  unpainted: "Bausatz",
  painted: "Fertigmodell",
};

/** "unpainted" → "Bausatz". */
export function finishName(code: string): string {
  return FINISH_NAMES[code] ?? code;
}

type PhotoMarkProps = {
  /** What the model is sold as, by name ("Bausatz", "Fertigmodell"); both when it comes as both. */
  finishes: readonly string[];
  size?: "small" | "default";
  className?: string;
};

/**
 * The tag in the bottom right corner of a model photo: the wordmark and what the model
 * is sold as. A small edged card with the hard shadow of the house, so it stands on the
 * light stage like a label on a box. It lies over the photo, so every photo carries it,
 * new ones too, and the photo itself stays clean (for eBay, Google and the newsletter).
 */
export function PhotoMark({
  finishes,
  size = "default",
  className,
}: PhotoMarkProps) {
  const small = size === "small";
  return (
    <div
      className={cn(
        "pointer-events-none absolute right-3 bottom-3 flex items-center border border-ink bg-surface",
        "shadow-[2px_2px_0_var(--ink)] select-none",
        small
          ? "gap-2 px-2 py-1"
          : "gap-2.5 px-3 py-1.5 sm:right-4 sm:bottom-4",
        className,
      )}
    >
      <Wordmark
        name="adp-Modelle"
        className={small ? "text-[0.8125rem]" : "text-[0.9375rem]"}
      />
      {finishes.length > 0 ? (
        <>
          <span aria-hidden="true" className="h-3.5 w-px bg-line-strong" />
          <span
            className={cn(
              "font-semibold tracking-[0.06em] text-ink uppercase",
              small ? "text-[0.625rem]" : "text-[0.6875rem]",
            )}
          >
            {finishes.join(" · ")}
          </span>
        </>
      ) : null}
    </div>
  );
}
