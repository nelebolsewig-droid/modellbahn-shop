"use client";

import { LogoMark } from "@/components/site/logo-mark";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PendingNotice } from "@/components/ui/pending-notice";
import { useStaffLogout } from "@/lib/api/generated/admin-auth/admin-auth";
import type { StaffOut } from "@/lib/api/generated/model";
import { SHOP_NAME } from "@/lib/config";
import { formatWeekdayDate, greetingFor } from "@/lib/format";
import { errorMessage } from "@/lib/i18n/problems";
import { STAFF_AREA } from "@/lib/navigation";
import { useStaffSession, useStaffSessionCache } from "@/lib/session/staff";
import { useProtectedArea } from "@/lib/session/use-session-redirects";
import { STAFF_ROLE_LABELS } from "@/lib/staff";

import { EventFeed } from "./event-feed";
import { StaffPasswordDialog } from "./staff-password-dialog";
import { SystemStatus } from "./system-status";

/** The admin start page: who is on duty, the live event feed and the system status. */
export function Stellwerk() {
  const session = useStaffSession();
  const cache = useStaffSessionCache();
  const { leave } = useProtectedArea(session, cache, STAFF_AREA);

  switch (session.status) {
    case "loading":
    case "anonymous":
      return (
        <main className="mx-auto max-w-7xl px-5 py-16 sm:px-8">
          <PendingNotice>Das Stellwerk wird geöffnet …</PendingNotice>
        </main>
      );
    case "error":
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
    case "authenticated":
      return (
        <Desk
          staff={session.account}
          onLoggedOut={() => leave(STAFF_AREA.login)}
          // The browser gave up on the live feed. If the session has ended, re-checking
          // it sends the page to the login; otherwise the feed retries on its own.
          onStreamClosed={() => void cache.revalidate()}
        />
      );
  }
}

type DeskProps = {
  staff: StaffOut;
  onLoggedOut: () => void;
  onStreamClosed: () => void;
};

function Desk({ staff, onLoggedOut, onStreamClosed }: DeskProps) {
  const logout = useStaffLogout();
  const now = new Date();

  return (
    <>
      <header className="rule-b border-line">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-5 py-4 sm:px-8">
          <div className="flex items-center gap-3">
            <LogoMark />
            <div>
              <p className="label-caps text-ink-muted">{SHOP_NAME}</p>
              <p className="font-display text-2xl leading-none font-semibold tracking-display uppercase">
                Stellwerk
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <StaffPasswordDialog />
            <Button
              type="button"
              variant="secondary"
              size="sm"
              disabled={logout.isPending}
              aria-busy={logout.isPending || undefined}
              onClick={() => logout.mutate(undefined, { onSuccess: onLoggedOut })}
            >
              {logout.isPending ? "Abmelden …" : "Abmelden"}
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-5 py-10 sm:px-8">
        <p role="alert" className="text-sm font-medium text-danger not-empty:mb-6">
          {logout.isError ? errorMessage(logout.error) : null}
        </p>
        <p className="label-caps text-ink-muted">Dienst · {formatWeekdayDate(now)}</p>
        <h1 className="mt-3 text-4xl break-words sm:text-5xl">
          {greetingFor(now)}, {staff.display_name}
        </h1>
        <p className="mt-3 flex flex-wrap items-center gap-2 text-ink-muted">
          Angemeldet als <Badge tone="warning">{STAFF_ROLE_LABELS[staff.role]}</Badge>
          <span className="break-all">{staff.email}</span>
        </p>

        <div className="mt-10 grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
          <EventFeed onStreamClosed={onStreamClosed} />
          <SystemStatus />
        </div>
      </main>
    </>
  );
}
