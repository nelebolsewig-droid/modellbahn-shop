"use client";

import { useMutation } from "@tanstack/react-query";
import type { Route } from "next";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { ConnectionLamp } from "@/components/admin/connection-lamp";
import { Panel } from "@/components/admin/panel";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { PendingNotice } from "@/components/ui/pending-notice";
import { SignalLamp, type LampColor } from "@/components/ui/signal-lamp";
import { deletePrinter } from "@/lib/api/generated/admin-manufacturing/admin-manufacturing";
import type { PrinterRecordOut, PrinterStatus, StaffRole, StatusReportOut } from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";
import { formatEventTime, formatLongDate } from "@/lib/format";
import { errorMessage } from "@/lib/i18n/problems";
import { MAY_PLAN, PRINTER_STATE_PHRASES, PRINTER_STATUS_LABELS, TECHNOLOGY_LABELS } from "@/lib/manufacturing/hall";
import { ADMIN_EVENTS_URL, isManufacturingEvent, MANUFACTURING_EVENT_TYPES } from "@/lib/realtime/events";
import { useEventStream } from "@/lib/realtime/use-event-stream";

import { PrinterCard } from "./printer-card";
import { PrinterDialog } from "./printer-dialogs";
import { JobRow } from "./printer-hall";
import { useHall, useManufacturingRefresh, useNow, usePrinterRecord } from "./use-manufacturing";

const HALL = "/admin/fertigung" as Route;

const STATUS_LAMPS = {
  in_service: "green",
  defective: "red",
  in_repair: "yellow",
  retired: "off",
} as const satisfies Record<PrinterStatus, LampColor>;

type PrinterDeskProps = { printerId: string; staffRole: StaffRole; onStreamClosed: () => void };

/** One printer: its card, its history of reports and its latest plates. */
export function PrinterDesk({ printerId, staffRole, onStreamClosed }: PrinterDeskProps) {
  const record = usePrinterRecord(printerId);
  const hall = useHall();
  const refresh = useManufacturingRefresh();
  const now = useNow(30_000);
  const mayPlan = MAY_PLAN.has(staffRole);
  const stream = useEventStream({
    url: ADMIN_EVENTS_URL,
    eventTypes: MANUFACTURING_EVENT_TYPES,
    onMessage(data) {
      if (isManufacturingEvent(data)) refresh();
    },
    onClosed: onStreamClosed,
  });

  if (record.isPending) {
    return <PendingNotice>Der Drucker wird geladen …</PendingNotice>;
  }
  if (record.isError) {
    return (
      <div className="space-y-4">
        <Alert tone="danger" title="Der Drucker konnte nicht geladen werden">
          <p>{errorMessage(record.error)}</p>
        </Alert>
        <Button asChild variant="secondary">
          <Link href={HALL}>Zur Druckerhalle</Link>
        </Button>
      </div>
    );
  }

  const printer = record.data;
  return (
    <>
      <Link href={HALL} className="text-small text-accent hover:underline">
        ← Druckerhalle
      </Link>
      <div className="mt-4 flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="label-caps text-ink-tertiary">Drucker · {TECHNOLOGY_LABELS[printer.technology]}</p>
          <h1 className="mt-3 flex flex-wrap items-baseline gap-x-4 text-heading sm:text-title">
            <span className="font-mono tracking-wider">{printer.code}</span>
            {printer.name ? <span className="font-extralight text-ink-secondary">{printer.name}</span> : null}
          </h1>
        </div>
        <ConnectionLamp state={stream.state} onReconnect={stream.reconnect} />
      </div>
      {mayPlan ? <Actions printer={printer} /> : null}

      <div className="mt-8 grid items-start gap-6 lg:grid-cols-[22rem_minmax(0,1fr)]">
        <div className="space-y-6">
          <PrinterCard desk={printer} printers={hall.data?.printers ?? [printer]} mayPlan={mayPlan} now={now} />
          <Panel title="Daten" code="DRU 02">
            <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-6 gap-y-2 text-small">
              <dt className="text-ink-tertiary">Drucktechnik</dt>
              <dd>{TECHNOLOGY_LABELS[printer.technology]}</dd>
              <dt className="text-ink-tertiary">Modell</dt>
              <dd>{printer.model || "–"}</dd>
              <dt className="text-ink-tertiary">Bauraum</dt>
              <dd className="tabular-nums">
                {printer.build_x_mm !== null
                  ? `${printer.build_x_mm} × ${printer.build_y_mm} × ${printer.build_z_mm} mm`
                  : "–"}
              </dd>
              <dt className="text-ink-tertiary">Dabei seit</dt>
              <dd>{formatLongDate(new Date(printer.created_at))}</dd>
            </dl>
            {printer.notes ? (
              <p className="mt-4 text-small whitespace-pre-line text-ink-secondary">{printer.notes}</p>
            ) : null}
          </Panel>
        </div>
        <div className="space-y-6">
          <Panel title="Verlauf" code="DRU 03">
            <History reports={printer.history} />
          </Panel>
          <Panel title="Letzte Drucke" code="DRU 04">
            {printer.jobs.length === 0 ? (
              <p className="text-small text-ink-secondary">Auf diesem Drucker lag noch keine Platte.</p>
            ) : (
              <ul className="divide-y divide-line">
                {printer.jobs.map((job) => (
                  <JobRow key={job.id} job={job} actions={false} />
                ))}
              </ul>
            )}
          </Panel>
        </div>
      </div>
    </>
  );
}

function Actions({ printer }: { printer: PrinterRecordOut }) {
  const router = useRouter();
  const refresh = useManufacturingRefresh();
  const remove = useMutation<void, ApiProblem>({
    mutationFn: () => deletePrinter(printer.id),
    onSuccess() {
      refresh();
      router.push(HALL);
    },
  });
  return (
    <div className="mt-6 flex flex-wrap items-center gap-2">
      <PrinterDialog
        printer={printer}
        trigger={
          <Button type="button" size="sm" variant="secondary">
            Bearbeiten
          </Button>
        }
      />
      {printer.jobs.length === 0 ? (
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="text-danger hover:bg-danger-subtle hover:text-danger"
          disabled={remove.isPending}
          onClick={() => {
            if (window.confirm(`Drucker ${printer.code} entfernen?`)) remove.mutate();
          }}
        >
          Entfernen
        </Button>
      ) : null}
      <span role="alert" className="text-hint text-danger">
        {remove.isError ? errorMessage(remove.error) : null}
      </span>
    </div>
  );
}

/** The reports of a printer as a line of lamps, the newest on top. */
function History({ reports }: { reports: readonly StatusReportOut[] }) {
  if (reports.length === 0) {
    return <p className="text-small text-ink-secondary">Noch keine Meldung.</p>;
  }
  return (
    <ol className="relative">
      {reports.map((report, index) => (
        <li key={report.id} className="relative grid grid-cols-[1.5rem_minmax(0,1fr)] gap-x-3 pb-5 last:pb-0">
          {index < reports.length - 1 ? (
            <span aria-hidden="true" className="absolute top-5 bottom-0 left-[11.5px] w-px bg-line-strong" />
          ) : null}
          <span className="relative mt-0.5 flex size-6 items-center justify-center rounded-full border border-line bg-surface">
            <SignalLamp color={STATUS_LAMPS[report.to_status]} />
          </span>
          <div className="min-w-0">
            <p className="text-small">
              <span className="font-medium">{PRINTER_STATUS_LABELS[report.to_status]}</span>
              {report.from_status === null ? (
                <span className="text-ink-tertiary"> · angelegt</span>
              ) : report.from_status === report.to_status ? (
                <span className="text-ink-tertiary"> · neuer Hinweis</span>
              ) : (
                <span className="text-ink-tertiary"> · vorher {PRINTER_STATE_PHRASES[report.from_status]}</span>
              )}
            </p>
            {report.note ? <p className="mt-0.5 text-small text-ink-secondary">„{report.note}“</p> : null}
            <p className="mt-0.5 text-hint text-ink-tertiary">
              {formatEventTime(new Date(report.occurred_at))}
              {report.staff_name ? ` · ${report.staff_name}` : ""}
            </p>
          </div>
        </li>
      ))}
    </ol>
  );
}
