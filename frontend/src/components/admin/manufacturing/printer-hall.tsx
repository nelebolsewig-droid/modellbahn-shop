"use client";

import type { Route } from "next";
import Link from "next/link";

import { ConnectionLamp } from "@/components/admin/connection-lamp";
import { Panel } from "@/components/admin/panel";
import { Button } from "@/components/ui/button";
import { PendingNotice } from "@/components/ui/pending-notice";
import { SignalLamp, type LampColor } from "@/components/ui/signal-lamp";
import { StatusBadge } from "@/components/ui/status-badge";
import type { HallCountsOut, PrintJobOut, StaffRole } from "@/lib/api/generated/model";
import { formatClock, formatEventTime } from "@/lib/format";
import { errorMessage } from "@/lib/i18n/problems";
import { JOB_STATUS_LABELS, JOB_STATUS_TONES, jobTitle, MAY_PLAN, plateSummary } from "@/lib/manufacturing/hall";
import { ADMIN_EVENTS_URL, isManufacturingEvent, MANUFACTURING_EVENT_TYPES } from "@/lib/realtime/events";
import { useEventStream } from "@/lib/realtime/use-event-stream";
import { cn } from "@/lib/utils";

import { CompleteJobDialog, FailJobDialog, PlanJobDialog } from "./job-dialogs";
import { GRID_SHEET, PrinterCard, printerHref } from "./printer-card";
import { PrinterDialog } from "./printer-dialogs";
import { PrinterGlyph } from "./printer-glyph";
import { RECENT_JOBS, useHall, useJobs, useManufacturingRefresh, useNow } from "./use-manufacturing";

const PARTS_PAGE = "/admin/fertigung/teile" as Route;

/**
 * The printer hall: every printer with its lamp, its plate and its queue, the plates in
 * post-processing and the latest finished ones, all live. A report of a defect on the
 * phone shows up here at once.
 */
export function PrinterHall({ staffRole, onStreamClosed }: { staffRole: StaffRole; onStreamClosed: () => void }) {
  const hall = useHall();
  const recent = useJobs(RECENT_JOBS);
  const refresh = useManufacturingRefresh();
  const now = useNow(30_000);
  const mayPlan = MAY_PLAN.has(staffRole);
  const stream = useEventStream({
    url: ADMIN_EVENTS_URL,
    eventTypes: MANUFACTURING_EVENT_TYPES,
    onMessage(data) {
      if (isManufacturingEvent(data)) {
        refresh();
      }
    },
    onClosed: onStreamClosed,
  });
  const printers = hall.data?.printers ?? [];
  // Retired printers keep their history but no longer stand in the hall.
  const working = printers.filter((desk) => desk.status !== "retired");
  const retired = printers.filter((desk) => desk.status === "retired");

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="label-caps text-ink-tertiary">Werkstatt</p>
          <h1 className="mt-3 text-heading sm:text-title">Fertigung</h1>
        </div>
        <ConnectionLamp state={stream.state} onReconnect={stream.reconnect} />
      </div>
      <div className="mt-6 flex flex-wrap gap-2">
        {mayPlan && printers.length > 0 ? (
          <PlanJobDialog
            printers={printers}
            trigger={
              <Button type="button" size="sm">
                Druckauftrag planen
              </Button>
            }
          />
        ) : null}
        {mayPlan ? (
          <PrinterDialog
            trigger={
              <Button type="button" size="sm" variant="secondary">
                Drucker hinzufügen
              </Button>
            }
          />
        ) : null}
        <Button asChild size="sm" variant="ghost">
          <Link href={PARTS_PAGE}>Teile &amp; Material</Link>
        </Button>
      </div>

      {hall.isPending ? (
        <PendingNotice className="mt-8">Die Druckerhalle wird geladen …</PendingNotice>
      ) : hall.isError ? (
        <p role="alert" className="mt-8 text-small text-danger">
          {errorMessage(hall.error)}
        </p>
      ) : printers.length === 0 ? (
        <EmptyHall mayPlan={mayPlan} />
      ) : (
        <>
          <HallBoard counts={hall.data.counts} />
          <section aria-label="Drucker" className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {working.map((desk) => (
              <PrinterCard key={desk.id} desk={desk} printers={printers} mayPlan={mayPlan} now={now} />
            ))}
          </section>
          {retired.length > 0 ? (
            <p className="mt-4 flex flex-wrap items-baseline gap-x-2 gap-y-1 text-hint text-ink-tertiary">
              <span>Ausgemustert:</span>
              {retired.map((desk) => (
                <Link
                  key={desk.id}
                  href={printerHref(desk.id)}
                  className="rounded-xs border border-line px-1.5 font-mono text-ink-secondary hover:border-ink-secondary"
                >
                  {desk.code}
                </Link>
              ))}
            </p>
          ) : null}
          <div className="mt-8 grid items-start gap-6 lg:grid-cols-2">
            <Panel title="Nachbearbeitung" code="FER 02">
              {hall.data.post_processing.length === 0 ? (
                <p className="text-small text-ink-secondary">
                  Nichts in der Nachbearbeitung. Abgenommene Platten warten hier aufs Waschen, Aushärten oder
                  Entstützen.
                </p>
              ) : (
                <ul className="divide-y divide-line">
                  {hall.data.post_processing.map((job) => (
                    <JobRow key={job.id} job={job} actions />
                  ))}
                </ul>
              )}
            </Panel>
            <Panel title="Zuletzt fertig" code="FER 03">
              {recent.isPending ? (
                <PendingNotice>Wird geladen …</PendingNotice>
              ) : recent.isError ? (
                <p role="alert" className="text-small text-danger">
                  {errorMessage(recent.error)}
                </p>
              ) : recent.data.length === 0 ? (
                <p className="text-small text-ink-secondary">Noch keine Platte fertig gemeldet.</p>
              ) : (
                <ul className="divide-y divide-line">
                  {recent.data.map((job) => (
                    <JobRow key={job.id} job={job} actions={false} />
                  ))}
                </ul>
              )}
            </Panel>
          </div>
        </>
      )}
    </>
  );
}

const BOARD: readonly { key: keyof HallCountsOut; label: string; lamp: LampColor }[] = [
  { key: "in_service", label: "In Betrieb", lamp: "green" },
  { key: "printing", label: "Drucken", lamp: "blue" },
  { key: "queued", label: "Warten", lamp: "off" },
  { key: "post_processing", label: "Nachbearbeitung", lamp: "yellow" },
  { key: "defective", label: "Defekt", lamp: "red" },
  { key: "in_repair", label: "In Reparatur", lamp: "yellow" },
];

/** The hall at a glance, like the indicator board of a signal box. */
function HallBoard({ counts }: { counts: HallCountsOut }) {
  return (
    // The 1 px gaps show the line colour behind the fields: hairlines for any number of columns.
    <dl className="mt-8 grid grid-cols-2 gap-px overflow-hidden rounded-md border border-line bg-line sm:grid-cols-3 lg:grid-cols-6">
      {BOARD.map((entry) => {
        const value = counts[entry.key];
        const quiet = value === 0 && (entry.key === "defective" || entry.key === "in_repair");
        return (
          <div key={entry.key} className="flex flex-col gap-1 bg-surface px-4 py-3 sm:px-5 sm:py-4">
            <dt className="flex items-center gap-1.5 text-hint text-ink-secondary">
              <SignalLamp color={quiet ? "off" : entry.lamp} className="-ml-1" />
              <span className="truncate">{entry.label}</span>
            </dt>
            <dd className="text-title font-extralight tabular-nums">{value}</dd>
          </div>
        );
      })}
    </dl>
  );
}

/** What happened to a plate last, and when: "22 von 24 gut · 20:14:49". */
function jobMoment(job: PrintJobOut): string {
  const at = (value: string | null) => formatEventTime(new Date(value ?? job.created_at));
  switch (job.status) {
    case "done":
      return `${job.lines.reduce((sum, line) => sum + line.good, 0)} von ${job.part_count} gut · ${at(job.finished_at)}`;
    case "failed":
      return `${job.failure_reason || "Fehldruck"} · ${at(job.finished_at)}`;
    case "cancelled":
      return `gestrichen · ${at(job.finished_at)}`;
    case "post_processing":
      return `abgenommen · ${at(job.printed_at)}`;
    case "printing":
      return `läuft seit ${formatClock(new Date(job.started_at ?? job.created_at))}`;
    default:
      return `geplant · ${at(job.created_at)}`;
  }
}

export function JobRow({ job, actions }: { job: PrintJobOut; actions: boolean }) {
  return (
    <li className="grid gap-x-4 gap-y-2 py-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
      <div className="min-w-0">
        <p className="flex flex-wrap items-baseline gap-x-2 text-small">
          <span className="font-medium">{jobTitle(job)}</span>
          <Link
            href={printerHref(job.printer.id)}
            className="rounded-xs border border-line px-1.5 font-mono text-hint text-ink-secondary hover:border-ink-secondary"
          >
            {job.printer.code}
          </Link>
          <StatusBadge tone={JOB_STATUS_TONES[job.status]}>{JOB_STATUS_LABELS[job.status]}</StatusBadge>
        </p>
        <p className="mt-0.5 truncate text-hint text-ink-secondary">{plateSummary(job, 2)}</p>
        <p className="text-hint text-ink-tertiary">{jobMoment(job)}</p>
      </div>
      {actions ? (
        <div className="flex gap-2">
          <CompleteJobDialog
            job={job}
            trigger={
              <Button type="button" size="sm">
                Fertig
              </Button>
            }
          />
          <FailJobDialog
            job={job}
            trigger={
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="text-danger hover:bg-danger-subtle hover:text-danger"
              >
                Fehldruck
              </Button>
            }
          />
        </div>
      ) : null}
    </li>
  );
}

function EmptyHall({ mayPlan }: { mayPlan: boolean }) {
  return (
    <section className="mt-8 grid items-center gap-8 rounded-md border border-line bg-surface p-6 sm:p-10 md:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
      <div className="max-w-md">
        <h2 className="text-heading">Noch keine Drucker</h2>
        <p className="mt-3 text-ink-secondary">
          Leg die Drucker der Werkstatt mit dem Code von ihrem Etikett an. Danach siehst du hier jeden mit seinem
          Zustand und dem Druck, der gerade läuft.
        </p>
        {mayPlan ? (
          <PrinterDialog
            trigger={
              <Button type="button" className="mt-6">
                Ersten Drucker anlegen
              </Button>
            }
          />
        ) : null}
      </div>
      <div className={cn("grid grid-cols-2 gap-6 rounded-sm px-6 py-5", GRID_SHEET)}>
        <PrinterGlyph technology="resin" fraction={0.6} />
        <PrinterGlyph technology="fdm" fraction={0.35} />
      </div>
    </section>
  );
}
