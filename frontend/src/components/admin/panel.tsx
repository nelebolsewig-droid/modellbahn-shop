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
      className={cn("rounded-md border border-line bg-surface", className)}
    >
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3">
        <div className="flex items-baseline gap-3">
          {code ? (
            <span className="font-mono text-hint text-ink-tertiary" aria-hidden="true">
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
