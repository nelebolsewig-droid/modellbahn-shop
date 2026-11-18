import { useId, type ReactNode } from "react";

import { cn } from "@/lib/utils";

type PanelProps = {
  title: string;
  /** Anchor, so a "next step" elsewhere on the page can lead here. */
  id?: string;
  /** Status or controls in the panel's header row. */
  actions?: ReactNode;
  className?: string;
  children: ReactNode;
};

/** A field of the Stellwerk desk. */
export function Panel({ title, id, actions, className, children }: PanelProps) {
  const headingId = useId();
  return (
    <section
      id={id}
      aria-labelledby={headingId}
      className={cn("scroll-mt-24 rounded-md border border-line bg-surface", className)}
    >
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3">
        <h2 id={headingId} className="text-body font-medium tracking-normal">
          {title}
        </h2>
        {actions}
      </header>
      <div className="p-5">{children}</div>
    </section>
  );
}
