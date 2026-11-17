import { useId, type ReactNode } from "react";

import { cn } from "@/lib/utils";

type PanelProps = {
  title: string;
  /** Mono caption next to the title, like the field labels of a signal-box desk. */
  code?: string;
  /** Status or controls in the panel's header row. */
  actions?: ReactNode;
  className?: string;
  children: ReactNode;
};

/** A field of the Stellwerk desk. */
export function Panel({ title, code, actions, className, children }: PanelProps) {
  const headingId = useId();
  return (
    <section
      aria-labelledby={headingId}
      className={cn("relative overflow-hidden rounded-md border border-line bg-surface", className)}
    >
      {/* The section's colour along the top edge. */}
      <span aria-hidden="true" className="absolute inset-x-0 top-0 h-[3px] bg-section" />
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3">
        <div className="flex items-center gap-3">
          {code ? (
            <span
              className="rounded-xs bg-[color-mix(in_srgb,var(--color-section)_12%,var(--surface))] px-1.5 py-0.5 font-mono text-hint text-section"
              aria-hidden="true"
            >
              {code}
            </span>
          ) : null}
          <h2 id={headingId} className="text-body font-medium tracking-normal">
            {title}
          </h2>
        </div>
        {actions}
      </header>
      <div className="p-5">{children}</div>
    </section>
  );
}
