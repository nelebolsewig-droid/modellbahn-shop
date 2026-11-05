import type { ReactNode } from "react";

/**
 * Typography of the legal pages (AGB, Widerruf, Datenschutz): a narrow column of
 * numbered sections, set like the notes field of a technical drawing.
 */
export function LegalText({ children }: { children: ReactNode }) {
  return <div className="mt-12 max-w-3xl space-y-12 leading-7 text-ink-secondary">{children}</div>;
}

type LegalSectionProps = {
  id: string;
  title: string;
  /** "§ 3" or "3": shown in the margin of the heading. */
  mark?: string;
  children: ReactNode;
};

export function LegalSection({ id, title, mark, children }: LegalSectionProps) {
  return (
    <section aria-labelledby={id} className="scroll-mt-24">
      <h2 id={id} className="flex items-baseline gap-3 text-heading text-ink">
        {mark ? <span className="font-mono text-small text-ink-tertiary">{mark}</span> : null}
        <span>{title}</span>
      </h2>
      <div className="mt-4 space-y-4">{children}</div>
    </section>
  );
}

export function LegalSubheading({ children }: { children: ReactNode }) {
  return <h3 className="pt-2 font-medium text-ink">{children}</h3>;
}

/** "Stand: November 2026", set small below the text. */
export function LegalStand({ children }: { children: ReactNode }) {
  return <p className="font-mono text-hint text-ink-tertiary">Stand: {children}</p>;
}
