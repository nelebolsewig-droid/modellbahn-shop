"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { Wordmark } from "@/components/site/wordmark";
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
import { OFFICE_ROLES, STAFF_ROLE_LABELS } from "@/lib/staff";

import { useToMakeCount } from "./sales/to-make-list";
import { StaffPasswordDialog } from "./staff-password-dialog";
import { PhoneBar, RailNav, ScanButton } from "./stellwerk-nav";

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

/**
 * Frame of every page of the Stellwerk: on a desk a rail with navigation, Scannen, password
 * and logout; on the phone a low header and a bar at the bottom. Each role sees only the entries it can use.
 * Visitors without a valid staff session go to the login and come back afterwards.
 */
export function AdminShell({ children }: AdminShellProps) {
  const session = useStaffSession();
  const cache = useStaffSessionCache();
  const { leave } = useProtectedArea(session, cache, STAFF_AREA);
  const logout = useStaffLogout();
  const pathname = usePathname();
  // Owner and staff see beside Bestellungen how many pieces wait for the workshop.
  const toMake = useToMakeCount(session.status === "authenticated" && OFFICE_ROLES.has(session.account.role));
  const counts = toMake ? { orders: toMake } : undefined;

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

  const { role, display_name: displayName } = session.account;
  return (
    // --stellwerk-bar: the height of the phone's bottom bar, kept free at the end of the
    // page and above sticky action bars (none on a desk).
    <div className="[--stellwerk-bar:calc(4rem_+_env(safe-area-inset-bottom))] lg:grid lg:grid-cols-[14.5rem_minmax(0,1fr)] lg:[--stellwerk-bar:0px]">
      {/* On a desk: a rail at the left edge with the wordmark, the places and Scannen at
          its foot (ADR 0030). On the phone: wordmark and account actions in one low row,
          so the scanner's camera starts high up; the places are in the bar at the bottom. */}
      <header className="flex items-center justify-between gap-x-6 border-b border-line bg-surface px-5 py-3 sm:px-8 lg:sticky lg:top-0 lg:h-dvh lg:flex-col lg:items-stretch lg:justify-start lg:gap-0 lg:overflow-y-auto lg:border-r lg:border-b-0 lg:p-0">
        <Link href="/admin" className="block lg:px-5 lg:pt-6 lg:pb-6">
          <Wordmark name={SHOP_NAME} className="text-[1.25rem] lg:text-[1.375rem]" />
          <span className="mt-1 block label-caps text-ink-secondary lg:mt-1.5">Stellwerk</span>
        </Link>
        <RailNav role={role} pathname={pathname} counts={counts} />
        <div className="flex items-center gap-2 lg:mt-auto lg:flex-col lg:items-stretch lg:gap-0 lg:p-5">
          <ScanButton pathname={pathname} />
          <p className="mt-6 text-small text-ink-secondary max-lg:hidden">
            {displayName} · {STAFF_ROLE_LABELS[role]}
          </p>
          <div className="flex items-center gap-2 lg:mt-2 lg:-ml-4 lg:flex-wrap lg:gap-0">
            <Button asChild variant="ghost" size="sm" className="max-sm:px-2.5">
              <Link href="/admin/hilfe" aria-current={pathname === "/admin/hilfe" ? "page" : undefined}>
                {/* A question mark on the phone, beside the key of the password. */}
                <svg aria-hidden="true" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" className="size-5 sm:hidden">
                  <circle cx="10" cy="10" r="7.5" />
                  <path d="M7.75 7.75a2.25 2.25 0 1 1 3.1 2.08c-.5.2-.85.68-.85 1.22v.45M10 14.25v.01" strokeLinecap="round" />
                </svg>
                <span className="max-sm:sr-only">Hilfe</span>
              </Link>
            </Button>
            <StaffPasswordDialog />
            <Button
              type="button"
              variant="secondary"
              size="sm"
              className="lg:border-0 lg:text-accent lg:hover:bg-accent-subtle"
              disabled={logout.isPending}
              aria-busy={logout.isPending || undefined}
              onClick={() => logout.mutate(undefined, { onSuccess: () => leave(STAFF_AREA.login) })}
            >
              {logout.isPending ? "Abmelden …" : "Abmelden"}
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-[90rem] min-w-0 px-5 pt-10 pb-[calc(2.5rem_+_var(--stellwerk-bar))] sm:px-8 lg:px-10 lg:pt-9">
        <p role="alert" className="text-small font-medium text-danger not-empty:mb-6">
          {logout.isError ? errorMessage(logout.error) : null}
        </p>
        {typeof children === "function"
          ? children({ staff: session.account, revalidate: () => void cache.revalidate() })
          : children}
      </main>
      <PhoneBar role={role} pathname={pathname} counts={counts} />
    </div>
  );
}
