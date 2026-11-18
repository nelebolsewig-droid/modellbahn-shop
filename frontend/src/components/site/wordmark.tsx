import { cn } from "@/lib/utils";

/**
 * The wordmark of the shop, as the workshop writes it: the part before the hyphen in
 * lower case, red, Times New Roman bold italic; the hyphen and the rest in ink, Arial bold
 * ("adp-Modelle", ADR 0030). A name without a hyphen is set in Arial bold as a whole.
 */
export function Wordmark({ name, className }: { name: string; className?: string }) {
  const cut = name.indexOf("-");
  const head = cut > 0 ? name.slice(0, cut) : "";
  const rest = cut > 0 ? name.slice(cut) : name;
  return (
    <span aria-label={name} className={cn("inline-block leading-none whitespace-nowrap text-ink", className)}>
      {head ? (
        <span aria-hidden="true" className="font-(family-name:--font-wordmark-serif) text-[1.12em] font-bold text-wordmark lowercase italic">
          {head}
        </span>
      ) : null}
      <span aria-hidden="true" className="font-(family-name:--font-wordmark-sans) font-bold">
        {rest}
      </span>
    </span>
  );
}
