"use client";

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

import { StaffPasswordDialog } from "./staff-password-dialog";
import { HeaderNav, PhoneBar, ScanButton } from "./stellwerk-nav";

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
 * Frame of every page of the Stellwerk: header with navigation, password and logout, on
 * the phone a bar at the bottom. Each role sees only the entries it can use.
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

  const role = session.account.role;
  return (
    // --stellwerk-bar: the height of the phone's bottom bar, kept free at the end of the
    // page and above sticky action bars (none on a desk).
    <div className="[--stellwerk-bar:calc(4rem_+_env(safe-area-inset-bottom))] sm:[--stellwerk-bar:0px]">
      <header className="border-b border-line bg-surface">
        {/* On the phone: logo and account actions in one low row, so the scanner's camera
            starts high up on the screen; the sections are in the bar at the bottom. */}
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-x-10 gap-y-3 px-5 py-3 sm:px-8 sm:py-4">
          <Link href="/admin" className="flex items-center gap-3 rounded-sm">
            <LogoMark />
            <span>
              <span className="block label-caps text-ink-tertiary max-sm:hidden">{SHOP_NAME}</span>
              <span className="block text-[1.25rem] leading-6 font-medium tracking-[-0.01em]">
                Stellwerk
              </span>
            </span>
          </Link>
          <HeaderNav role={role} pathname={pathname} />
          <div className="flex items-center gap-2">
            <ScanButton pathname={pathname} />
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
      <main className="mx-auto max-w-7xl px-5 pt-10 pb-[calc(2.5rem_+_var(--stellwerk-bar))] sm:px-8">
        <p role="alert" className="text-small font-medium text-danger not-empty:mb-6">
          {logout.isError ? errorMessage(logout.error) : null}
        </p>
        {typeof children === "function"
          ? children({ staff: session.account, revalidate: () => void cache.revalidate() })
          : children}
      </main>
      <PhoneBar role={role} pathname={pathname} />
    </div>
  );
}
