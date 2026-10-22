import type { ReactNode } from "react";

import { SiteFooter } from "./site-footer";
import { SiteHeader } from "./site-header";

const MAIN_ID = "inhalt";

/** Header, main content and footer of every shop page. */
export function ShopFrame({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href={`#${MAIN_ID}`}
        className="label-caps sr-only z-50 rounded-sm bg-primary px-4 py-3 text-primary-ink focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Zum Inhalt springen
      </a>
      <SiteHeader />
      <main id={MAIN_ID} tabIndex={-1} className="flex-1 outline-none">
        {children}
      </main>
      <SiteFooter />
    </div>
  );
}
