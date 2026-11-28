import { cn } from "@/lib/utils";

/** The ways to pay on SumUp's page, in the order customers look for them. */
export const SUMUP_METHODS = ["Karte", "PayPal", "Apple Pay", "Google Pay"] as const;

/** Means of payment as large, raised tiles, so they are seen at a glance before checkout. */
export function PaymentBadges({ className, size = "lg" }: { className?: string; size?: "md" | "lg" }) {
  return (
    <ul aria-label="Zahlungsarten" className={cn("flex flex-wrap gap-2", className)}>
      {SUMUP_METHODS.map((name) => (
        <li
          key={name}
          className={cn(
            "rounded-md border border-line-strong bg-canvas font-semibold text-ink",
            "shadow-[0_1px_0_var(--line-strong),0_3px_8px_-4px_rgb(38_33_30/0.35)]",
            size === "lg" ? "px-4 py-2 text-body" : "px-3 py-1.5 text-small",
          )}
        >
          {name}
        </li>
      ))}
    </ul>
  );
}
