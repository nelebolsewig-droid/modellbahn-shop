import { Wordmark } from "@/components/site/wordmark";
import { cn } from "@/lib/utils";

/** The names of the finishes as the shop says them; an unknown code is shown as it is. */
const FINISH_NAMES: Record<string, string> = { unpainted: "Bausatz", painted: "Fertigmodell", decal: "Decal" };

/** "unpainted" → "Bausatz". */
export function finishName(code: string): string {
  return FINISH_NAMES[code] ?? code;
}

type PhotoMarkProps = {
  /** What the model is sold as, by name ("Bausatz", "Fertigmodell"); both when it comes as both. */
  finishes: readonly string[];
  /** A partner label's name (e.g. "Vehicle World"); it then stands top left instead of adp's. */
  partner?: string | null;
  size?: "small" | "default";
};

/** Plain lettering on the light stage, no frame. */
const TAG = "pointer-events-none absolute flex items-center select-none";

/**
 * The tags on a model photo: the wordmark top left, what the model is sold as bottom
 * right. They lie over the photo, so every photo carries them, new ones too, and the
 * photo itself stays clean (for eBay, Google and the newsletter).
 */
export function PhotoMark({ finishes, partner, size = "default" }: PhotoMarkProps) {
  const small = size === "small";
  return (
    <>
      <div className={cn(TAG, small ? "top-4 left-4" : "top-4 left-4 sm:top-6 sm:left-6")}>
        {partner ? (
          <span className={cn("font-bold text-ink", small ? "text-[0.8125rem]" : "text-[0.9375rem]")}>{partner}</span>
        ) : (
          <Wordmark name="adp-Modelle" className={small ? "text-[0.8125rem]" : "text-[0.9375rem]"} />
        )}
      </div>
      {finishes.length > 0 ? (
        <div className={cn(TAG, small ? "right-4 bottom-4" : "right-4 bottom-4 sm:right-6 sm:bottom-6")}>
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
