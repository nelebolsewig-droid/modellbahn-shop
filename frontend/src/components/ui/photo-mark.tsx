import { Wordmark } from "@/components/site/wordmark";
import { cn } from "@/lib/utils";

/** The names of the finishes as the shop says them; an unknown code is shown as it is. */
const FINISH_NAMES: Record<string, string> = { unpainted: "Bausatz", painted: "Fertigmodell" };

/** "unpainted" → "Bausatz". */
export function finishName(code: string): string {
  return FINISH_NAMES[code] ?? code;
}

type PhotoMarkProps = {
  /** What the model is sold as, by name ("Bausatz", "Fertigmodell"); both when it comes as both. */
  finishes: readonly string[];
  size?: "small" | "default";
};

/** A small edged card with the hard shadow of the house, like a label on a box. */
const TAG = "pointer-events-none absolute flex items-center border border-ink bg-surface shadow-[2px_2px_0_var(--ink)] select-none";

/**
 * The tags on a model photo: the wordmark top left, what the model is sold as bottom
 * right. They lie over the photo, so every photo carries them, new ones too, and the
 * photo itself stays clean (for eBay, Google and the newsletter).
 */
export function PhotoMark({ finishes, size = "default" }: PhotoMarkProps) {
  const small = size === "small";
  const pad = small ? "px-2 py-1" : "px-3 py-1.5";
  return (
    <>
      <div className={cn(TAG, pad, small ? "top-3 left-3" : "top-3 left-3 sm:top-4 sm:left-4")}>
        <Wordmark name="adp-Modelle" className={small ? "text-[0.8125rem]" : "text-[0.9375rem]"} />
      </div>
      {finishes.length > 0 ? (
        <div className={cn(TAG, pad, small ? "right-3 bottom-3" : "right-3 bottom-3 sm:right-4 sm:bottom-4")}>
          <span
            className={cn(
              "font-semibold tracking-[0.06em] text-ink uppercase",
              small ? "text-[0.625rem]" : "text-[0.6875rem]",
            )}
          >
            {finishes.join(" · ")}
          </span>
        </div>
      ) : null}
    </>
  );
}
