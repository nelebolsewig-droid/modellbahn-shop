"use client";

import type { Route } from "next";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { LogoMark } from "@/components/site/logo-mark";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { PendingNotice } from "@/components/ui/pending-notice";
import { useStaffLogout } from "@/lib/api/generated/admin-auth/admin-auth";
import type { StaffOut } from "@/lib/api/generated/model";
import { SHOP_NAME } from "@/lib/config";
import { errorMessage } from "@/lib/i18n/problems";
import { STAFF_AREA } from "@/lib/navigation";
import { useStaffSession, useStaffSessionCache } from "@/lib/session/staff";
import { useProtectedArea } from "@/lib/session/use-session-redirects";
import { cn } from "@/lib/utils";

import { StaffPasswordDialog } from "./staff-password-dialog";

const SECTIONS = [
  { href: "/admin", label: "Übersicht", exact: true },
  { href: "/admin/bestellungen", label: "Bestellungen", exact: false },
  { href: "/admin/lager", label: "Lager", exact: false },
  { href: "/admin/scanner", label: "Scanner", exact: true },
  { href: "/admin/erfassen", label: "Erfassen", exact: true },
  { href: "/admin/katalog", label: "Katalog", exact: false },
  { href: "/admin/katalog/kategorien", label: "Kategorien", exact: true },
  { href: "/admin/katalog/massstaebe", label: "Maßstäbe", exact: true },
  { href: "/admin/messen", label: "Messen", exact: true },
] as const satisfies readonly { href: Route; label: string; exact: boolean }[];

export type AdminDesk = {
  staff: StaffOut;
  /** Re-checks the session, e.g. when an event stream was refused. */
  revalidate: () => void;
};

type AdminShellProps = {
  /**
   * The page, shown once the API has confirmed the staff session. A function gets the
   * staff member (only possible from client components); server pages pass elements.
   */
  children: ReactNode | ((desk: AdminDesk) => ReactNode);
};

function isActive(pathname: string, section: (typeof SECTIONS)[number]): boolean {
  if (section.exact) {
    return pathname === section.href;
  }
  // "Katalog" covers the products, not categories and scales, which have their own entries.
  const ownEntry = pathname.startsWith("/admin/katalog/kategorien") || pathname.startsWith("/admin/katalog/massstaebe");
  return pathname.startsWith(section.href) && !(section.href === "/admin/katalog" && ownEntry);
}

/**
 * Frame of every page of the Stellwerk: header with navigation, password and logout.
 * Visitors without a valid staff session go to the login and come back afterwards.
 */
export function AdminShell({ children }: AdminShellProps) {
  const session = useStaffSession();
  const cache = useStaffSessionCache();
  const { leave } = useProtectedArea(session, cache, STAFF_AREA);
  const logout = useStaffLogout();
  const pathname = usePathname();

  if (session.status === "loading" || session.status === "anonymous") {
    return (
      <main className="mx-auto max-w-7xl px-5 py-16 sm:px-8">
        <PendingNotice>Das Stellwerk wird geöffnet …</PendingNotice>
      </main>
    );
  }
  if (session.status === "error") {
    return (
      <main className="mx-auto max-w-3xl space-y-4 px-5 py-16 sm:px-8">
        <Alert tone="danger" title="Das Stellwerk konnte nicht geöffnet werden">
          <p>{errorMessage(session.error)}</p>
        </Alert>
        <Button type="button" variant="secondary" onClick={() => void cache.revalidate()}>
          Erneut versuchen
        </Button>
      </main>
    );
  }

  return (
    <>
      <header className="border-b border-line bg-surface">
        {/* On the phone: logo and actions in one row, the sections in a strip that scrolls
            sideways, so the scanner's camera starts high up on the screen. */}
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-x-10 gap-y-3 px-5 pt-3 sm:px-8 sm:py-4">
          <Link href="/admin" className="flex items-center gap-3 rounded-sm">
            <LogoMark />
            <span>
              <span className="block label-caps text-ink-tertiary max-sm:hidden">{SHOP_NAME}</span>
              <span className="block text-[1.25rem] leading-6 font-medium tracking-[-0.01em]">
                Stellwerk
              </span>
            </span>
          </Link>
          <nav
            aria-label="Stellwerk"
            className="order-3 -mx-5 w-[calc(100%+2.5rem)] overflow-x-auto px-5 pb-3 [scrollbar-width:none] sm:order-2 sm:mx-0 sm:w-auto sm:flex-1 sm:overflow-visible sm:px-0 sm:pb-0"
          >
            <ul className="flex gap-1 sm:flex-wrap">
              {SECTIONS.map((section) => {
                const active = isActive(pathname, section);
                return (
                  <li key={section.href} className="shrink-0">
                    <Link
                      href={section.href}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "inline-flex h-9 items-center rounded-full px-3 text-sm font-medium whitespace-nowrap transition-colors",
                        active ? "bg-selected text-on-selected" : "text-ink-secondary hover:bg-sunken hover:text-ink",
                      )}
                    >
                      {section.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>
          <div className="order-2 flex items-center gap-2 sm:order-3">
            <StaffPasswordDialog />
            <Button
              type="button"
              variant="secondary"
              size="sm"
              disabled={logout.isPending}
              aria-busy={logout.isPending || undefined}
              onClick={() => logout.mutate(undefined, { onSuccess: () => leave(STAFF_AREA.login) })}
            >
              {logout.isPending ? "Abmelden …" : "Abmelden"}
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-5 py-10 sm:px-8">
        <p role="alert" className="text-small font-medium text-danger not-empty:mb-6">
          {logout.isError ? errorMessage(logout.error) : null}
        </p>
        {typeof children === "function"
          ? children({ staff: session.account, revalidate: () => void cache.revalidate() })
          : children}
      </main>
    </>
  );
}
