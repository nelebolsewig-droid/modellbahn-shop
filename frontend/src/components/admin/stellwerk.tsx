"use client";

import { Badge } from "@/components/ui/badge";
import { formatWeekdayDate, greetingFor } from "@/lib/format";
import { STAFF_ROLE_LABELS } from "@/lib/staff";

import { AdminShell } from "./admin-shell";
import { EventFeed } from "./event-feed";
import { SystemStatus } from "./system-status";

/** The admin start page: who is on duty, the live event feed and the system status. */
export function Stellwerk() {
  return (
    <AdminShell>
      {({ staff, revalidate }) => {
        const now = new Date();
        return (
          <>
            <p className="label-caps text-ink-tertiary">Dienst · {formatWeekdayDate(now)}</p>
            <h1 className="mt-4 text-heading break-words sm:text-title">
              {greetingFor(now)}, {staff.display_name}
            </h1>
            <p className="mt-3 flex flex-wrap items-center gap-2 text-ink-secondary">
              Angemeldet als <Badge tone="accent">{STAFF_ROLE_LABELS[staff.role]}</Badge>
              <span className="break-all">{staff.email}</span>
            </p>

            <div className="mt-10 grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
              {/* The browser gave up on the live feed. If the session has ended,
                  re-checking it sends the page to the login; otherwise the feed retries. */}
              <EventFeed onStreamClosed={revalidate} />
              <SystemStatus />
            </div>
          </>
        );
      }}
    </AdminShell>
  );
}
