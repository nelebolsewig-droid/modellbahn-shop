import { cn } from "@/lib/utils";

/** The shop's mark: a light signal in its housing. Decorative; the name stands next to it. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={cn("size-8 shrink-0", className)}>
      <rect width="32" height="32" rx="5" className="fill-ink" />
      <circle cx="16" cy="11" r="5" className="fill-accent" />
      <circle cx="16" cy="11" r="5" className="fill-none stroke-surface" strokeWidth="1.5" />
      <rect x="9" y="21" width="14" height="3" rx="1.5" className="fill-surface" />
    </svg>
  );
}
