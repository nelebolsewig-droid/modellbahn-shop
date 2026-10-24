import type { ReactNode } from "react";

type PageHeadingProps = {
  /** Small caption above the title, e.g. the area of the site. */
  caption: string;
  title: ReactNode;
  children?: ReactNode;
  className?: string;
};

/** Caption, page title (the page's only h1) and an optional introduction. */
export function PageHeading({ caption, title, children, className }: PageHeadingProps) {
  return (
    <header className={className}>
      <p className="label-caps text-ink-tertiary">{caption}</p>
      <h1 className="mt-4 text-title sm:text-display">{title}</h1>
      {children ? (
        <div className="mt-6 max-w-xl space-y-3 text-body-lg text-ink-secondary">{children}</div>
      ) : null}
    </header>
  );
}
