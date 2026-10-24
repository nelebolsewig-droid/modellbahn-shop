import { cn } from "@/lib/utils";

/** The shop's mark: a light signal on an anthracite plate. Decorative; the name stands next to it. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={cn("size-8 shrink-0", className)}>
      <rect width="32" height="32" rx="8" className="fill-ink" />
      <circle cx="16" cy="12.5" r="5" className="fill-none stroke-on-selected" strokeWidth="1.5" />
      <circle cx="16" cy="12.5" r="1.75" className="fill-on-selected" />
      <rect x="9" y="22" width="14" height="2" rx="1" className="fill-on-selected" />
    </svg>
  );
}
