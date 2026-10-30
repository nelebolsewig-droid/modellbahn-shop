"use client";

import { useMutation } from "@tanstack/react-query";
import type { Route } from "next";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { SignalLamp } from "@/components/ui/signal-lamp";
import { startPrintJob, takeOffPrintJob } from "@/lib/api/generated/admin-manufacturing/admin-manufacturing";
import type { PrinterDeskOut, PrintJobOut } from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";
import { formatClock } from "@/lib/format";
import { errorMessage } from "@/lib/i18n/problems";
import {
  DESK_LAMPS,
  deskState,
  formatMinutes,
  jobTitle,
  plateProgress,
  plateSummary,
  PRINTER_STATUS_LABELS,
  sinceText,
  TECHNOLOGY_LABELS,
  type DeskState,
  type PlateProgress,
} from "@/lib/manufacturing/hall";
import { cn } from "@/lib/utils";

import { CompleteJobDialog, FailJobDialog, MoveJobDialog, PlanJobDialog } from "./job-dialogs";
import { PrinterGlyph } from "./printer-glyph";
import { StatusDialog } from "./printer-dialogs";
import { useManufacturingRefresh } from "./use-manufacturing";

/** The drawing sheet behind a printer: the stage colour with a faint construction grid. */
export const GRID_SHEET =
  "bg-stage bg-[image:linear-gradient(var(--drawing-grid)_1px,transparent_1px),linear-gradient(90deg,var(--drawing-grid)_1px,transparent_1px)] bg-[size:12px_12px] bg-[position:-1px_-1px]";

export function printerHref(printerId: string): Route {
  return `/admin/fertigung/drucker/${printerId}` as Route;
}

type PrinterCardProps = {
  desk: PrinterDeskOut;
  /** Every printer of the hall, to move waiting plates between them. */
  printers: readonly PrinterDeskOut[];
  mayPlan: boolean;
  now: Date;
};

/**
 * One printer of the hall, like a machine plate: the code from its label, its lamp, a
 * drawing in which the part grows with the plate's progress, and what can be done next.
 */
export function PrinterCard({ desk, printers, mayPlan, now }: PrinterCardProps) {
  const state = deskState(desk);
  const lamp = DESK_LAMPS[state];
  const progress = desk.printing ? plateProgress(desk.printing, now) : null;
  const down = state === "defective" || state === "in_repair" || state === "retired";
  const headingId = `printer-${desk.id}`;

  return (
    <article
      aria-labelledby={headingId}
      className={cn(
        "flex min-w-0 flex-col rounded-md border bg-surface transition-colors",
        state === "defective" ? "border-danger/40" : "border-line",
      )}
    >
      <header className="flex items-start justify-between gap-3 px-4 pt-4">
        <div className="min-w-0">
          <h3 id={headingId} className="text-body tracking-normal">
            <Link
              href={printerHref(desk.id)}
              className="inline-flex items-center rounded-xs border border-drawing-line px-2 py-0.5 font-mono text-[1.0625rem] leading-6 font-medium tracking-wider text-ink transition-colors hover:bg-sunken"
            >
              {desk.code}
            </Link>
            <span className="sr-only">{desk.name ? `, ${desk.name}` : ""}</span>
          </h3>
          <p className="mt-2 truncate text-small font-medium" aria-hidden={desk.name ? true : undefined}>
            {desk.name || TECHNOLOGY_LABELS[desk.technology]}
          </p>
          <p className="truncate text-hint text-ink-tertiary">
            {[TECHNOLOGY_LABELS[desk.technology], desk.model].filter(Boolean).join(" · ")}
          </p>
        </div>
        <p className="flex shrink-0 items-center gap-1.5 text-hint font-medium text-ink-secondary">
          <SignalLamp color={lamp.color} blinking={state === "printing"} />
          {lamp.label}
        </p>
      </header>

      <div className={cn("mx-4 mt-3 rounded-sm px-8 pt-3 pb-2", GRID_SHEET)}>
        <PrinterGlyph
          technology={desk.technology}
          fraction={desk.printing ? (progress?.fraction ?? 0.5) : null}
          muted={down}
          className="mx-auto max-w-56"
        />
      </div>

      <div className="flex flex-1 flex-col px-4 pt-3 pb-4">
        {desk.printing ? (
          <Printing job={desk.printing} progress={progress} />
        ) : down ? (
          <OutOfService desk={desk} state={state} now={now} />
        ) : (
          <Ready desk={desk} mayPlan={mayPlan} printers={printers} />
        )}
        {desk.queue.length > 0 && (desk.printing !== null || down) ? (
          <Queue desk={desk} printers={printers} mayPlan={mayPlan} />
        ) : null}
        <div className="mt-auto flex flex-wrap items-center gap-x-1 pt-3">
          {state === "retired" ? null : (
            <StatusDialog
              printer={desk}
              printing={desk.printing}
              trigger={
                <Button type="button" variant="ghost" size="sm" className="-ml-3">
                  Zustand melden
                </Button>
              }
            />
          )}
          <Button asChild variant="ghost" size="sm">
            <Link href={printerHref(desk.id)}>Verlauf</Link>
          </Button>
        </div>
      </div>
    </article>
  );
}

function Printing({ job, progress }: { job: PrintJobOut; progress: PlateProgress | null }) {
  const refresh = useManufacturingRefresh();
  const takeOff = useMutation<PrintJobOut, ApiProblem>({
    mutationFn: () => takeOffPrintJob(job.id),
    onSuccess: refresh,
  });
  const percent = progress ? Math.round(progress.fraction * 100) : null;
  return (
    <div>
      <p className="text-small">
        <span className="font-medium">{jobTitle(job)}</span>
        <span className="text-ink-secondary"> · {plateSummary(job, 2)}</span>
      </p>
      {progress ? (
        <>
          <div
            role="progressbar"
            aria-label={`Fortschritt ${jobTitle(job)}`}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={percent ?? 0}
            className="mt-3 h-1.5 overflow-hidden rounded-full bg-sunken"
          >
            <div
              className={cn(
                "h-full rounded-full transition-[width] duration-700",
                progress.overdue ? "bg-warning" : "bg-accent",
              )}
              style={{ width: `${percent}%` }}
            />
          </div>
          <p className="mt-1.5 flex justify-between gap-3 text-hint text-ink-tertiary tabular-nums">
            <span>{percent} %</span>
            <span className={progress.overdue ? "font-medium text-warning" : undefined}>
              {progress.overdue
                ? `${formatMinutes(-progress.remainingMinutes)} über der Zeit`
                : `noch ${formatMinutes(progress.remainingMinutes)} · bis ${formatClock(progress.endsAt)}`}
            </span>
          </p>
        </>
      ) : (
        <p className="mt-2 text-hint text-ink-tertiary">
          Läuft seit {job.started_at ? formatClock(new Date(job.started_at)) : "eben"}; Dauer unbekannt.
        </p>
      )}
      <div className="mt-3 grid grid-cols-2 gap-2">
        <CompleteJobDialog
          job={job}
          trigger={
            <Button type="button" size="sm">
              Fertig
            </Button>
          }
        />
        <Button
          type="button"
          size="sm"
          variant="secondary"
          disabled={takeOff.isPending}
          aria-busy={takeOff.isPending || undefined}
          onClick={() => takeOff.mutate()}
          title="Die Platte kommt in die Nachbearbeitung, der Drucker ist frei."
        >
          Abnehmen
        </Button>
      </div>
      <FailJobDialog
        job={job}
        trigger={
          <button type="button" className="mt-2 text-hint font-medium text-danger hover:underline">
            Fehldruck melden
          </button>
        }
      />
      <p role="alert" className="text-hint text-danger not-empty:mt-2">
        {takeOff.isError ? errorMessage(takeOff.error) : null}
      </p>
    </div>
  );
}

function Ready({
  desk,
  mayPlan,
  printers,
}: {
  desk: PrinterDeskOut;
  mayPlan: boolean;
  printers: readonly PrinterDeskOut[];
}) {
  const refresh = useManufacturingRefresh();
  const next = desk.queue[0] ?? null;
  const start = useMutation<PrintJobOut, ApiProblem>({
    mutationFn: () => startPrintJob(next?.id ?? ""),
    onSuccess: refresh,
  });
  if (next === null) {
    return (
      <div>
        <p className="text-small text-ink-secondary">Frei. Keine Platte in der Warteschlange.</p>
        {mayPlan ? (
          <PlanJobDialog
            printers={printers}
            printerId={desk.id}
            trigger={
              <Button type="button" size="sm" variant="secondary" className="mt-3">
                Platte planen
              </Button>
            }
          />
        ) : null}
      </div>
    );
  }
  return (
    <div>
      <p className="label-caps text-ink-tertiary">Als Nächstes</p>
      <p className="mt-1 text-small">
        <span className="font-medium">{jobTitle(next)}</span>
        <span className="text-ink-secondary"> · {plateSummary(next, 2)}</span>
      </p>
      <p className="text-hint text-ink-tertiary">
        {next.planned_minutes !== null ? `etwa ${formatMinutes(next.planned_minutes)}` : "Dauer unbekannt"}
        {desk.queue.length > 1 ? ` · danach ${desk.queue.length - 1} weitere` : ""}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          disabled={start.isPending}
          aria-busy={start.isPending || undefined}
          onClick={() => start.mutate()}
        >
          {start.isPending ? "Startet …" : `${jobTitle(next)} starten`}
        </Button>
        {mayPlan ? (
          <MoveJobDialog
            job={next}
            printers={printers}
            trigger={
              <Button type="button" size="sm" variant="secondary">
                Planen
              </Button>
            }
          />
        ) : null}
      </div>
      <p role="alert" className="text-hint text-danger not-empty:mt-2">
        {start.isError ? errorMessage(start.error) : null}
      </p>
    </div>
  );
}

function OutOfService({ desk, state, now }: { desk: PrinterDeskOut; state: DeskState; now: Date }) {
  const since = sinceText(new Date(desk.status_changed_at), now);
  return (
    <div>
      <p
        className={cn(
          "text-small font-medium",
          state === "defective" ? "text-danger" : state === "in_repair" ? "text-warning" : "text-ink-secondary",
        )}
      >
        {PRINTER_STATUS_LABELS[desk.status]} {since}
      </p>
      {desk.status_note ? <p className="mt-1 text-small text-ink-secondary">„{desk.status_note}“</p> : null}
      {state === "retired" ? null : (
        <StatusDialog
          printer={desk}
          printing={null}
          initialStatus="in_service"
          trigger={
            <Button type="button" size="sm" variant="secondary" className="mt-3">
              Wieder in Betrieb
            </Button>
          }
        />
      )}
    </div>
  );
}

function Queue({
  desk,
  printers,
  mayPlan,
}: {
  desk: PrinterDeskOut;
  printers: readonly PrinterDeskOut[];
  mayPlan: boolean;
}) {
  return (
    <div className="mt-4 border-t border-line pt-3">
      <p className="label-caps text-ink-tertiary">Warteschlange · {desk.queue.length}</p>
      <ul className="mt-1.5 space-y-1">
        {desk.queue.slice(0, 3).map((job) => (
          <li key={job.id} className="flex items-baseline justify-between gap-2 text-hint">
            <span className="min-w-0 truncate">
              <span className="font-medium text-ink">{jobTitle(job)}</span>
              <span className="text-ink-tertiary"> · {plateSummary(job, 1)}</span>
            </span>
            {mayPlan ? (
              <MoveJobDialog
                job={job}
                printers={printers}
                trigger={
                  <button type="button" className="shrink-0 text-accent hover:underline">
                    planen
                  </button>
                }
              />
            ) : null}
          </li>
        ))}
      </ul>
      {desk.queue.length > 3 ? (
        <p className="mt-1 text-hint text-ink-tertiary">und {desk.queue.length - 3} weitere</p>
      ) : null}
    </div>
  );
}
