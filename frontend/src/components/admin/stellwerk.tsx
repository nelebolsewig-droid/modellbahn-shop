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
            {/* The greeting on the night ground, with the palette's glows drifting behind it. */}
            <div className="relative overflow-hidden rounded-lg bg-night px-6 py-8 text-on-night sm:px-10 sm:py-10">
              <span
                aria-hidden="true"
                className="absolute -top-24 -right-16 size-80 animate-drift rounded-full bg-highlight opacity-40 blur-3xl"
              />
              <span
                aria-hidden="true"
                className="absolute -bottom-32 left-1/3 size-80 animate-drift-slow rounded-full bg-plum opacity-50 blur-3xl"
              />
              <div className="relative">
                <p className="label-caps text-on-night-muted">Dienst · {formatWeekdayDate(now)}</p>
                <h1 className="mt-4 text-heading break-words sm:text-title">
                  {greetingFor(now)}, <span className="font-normal text-spectrum-night">{staff.display_name}</span>
                </h1>
                <p className="mt-3 flex flex-wrap items-center gap-2 text-on-night-muted">
                  Angemeldet als <Badge tone="sun">{STAFF_ROLE_LABELS[staff.role]}</Badge>
                  <span className="break-all">{staff.email}</span>
                </p>
              </div>
            </div>

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
