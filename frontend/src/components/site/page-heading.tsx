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
      <p className="label-caps flex items-center gap-2 text-ink-muted">
        <span className="size-2 rounded-full bg-accent" aria-hidden="true" />
        {caption}
      </p>
      <h1 className="mt-4 text-5xl sm:text-6xl">{title}</h1>
      {children ? (
        <div className="mt-5 max-w-lg space-y-3 leading-7 text-ink-muted">{children}</div>
      ) : null}
    </header>
  );
}
