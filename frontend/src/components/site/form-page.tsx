import type { ReactNode } from "react";

import { PageHeading } from "./page-heading";

type FormPageProps = {
  caption: string;
  title: string;
  intro?: ReactNode;
  /** The form card. */
  children: ReactNode;
  /** Links below the card, e.g. "Noch kein Konto?". */
  footer?: ReactNode;
};

/** Layout of the account pages that consist of one form: heading left, form right. */
export function FormPage({ caption, title, intro, children, footer }: FormPageProps) {
  return (
    <div className="mx-auto grid max-w-6xl gap-10 px-5 py-12 sm:px-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,30rem)] lg:gap-16 lg:py-20">
      <PageHeading caption={caption} title={title}>
        {intro}
      </PageHeading>
      <div>
        <div className="rule rounded-md border-line-strong bg-surface-raised p-6 shadow-[inset_0_3px_0_0_var(--color-accent)] sm:p-8">
          {children}
        </div>
        {footer ? <div className="mt-6 space-y-2 text-sm text-ink-muted">{footer}</div> : null}
      </div>
    </div>
  );
}
