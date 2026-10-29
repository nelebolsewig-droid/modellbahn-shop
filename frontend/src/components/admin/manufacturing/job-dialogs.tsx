"use client";

import { useMutation } from "@tanstack/react-query";
import { useDeferredValue, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { QuantityStepper } from "@/components/ui/quantity-stepper";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  cancelPrintJob,
  completePrintJob,
  createPrintJob,
  failPrintJob,
  planPrintJob,
} from "@/lib/api/generated/admin-manufacturing/admin-manufacturing";
import type { PartOut, PrinterDeskOut, PrintJobOut } from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";
import { errorMessage } from "@/lib/i18n/problems";
import {
  estimateMinutes,
  formatMinutes,
  jobTitle,
  PRINTER_STATE_PHRASES,
  TECHNOLOGY_LABELS,
} from "@/lib/manufacturing/hall";
import { parseDuration } from "@/lib/validation/manufacturing";

import { useManufacturingRefresh, useParts } from "./use-manufacturing";

const DURATION_HINT = "Stunden:Minuten oder Minuten, wie im Slicer; leer: aus den Teilen geschätzt";

function DialogActions({ children, onCancel }: { children: ReactNode; onCancel: () => void }) {
  return (
    <div className="mt-6 flex flex-wrap justify-end gap-3">
      <Button type="button" variant="secondary" size="sm" onClick={onCancel}>
        Abbrechen
      </Button>
      {children}
    </div>
  );
}

function Failure({ error }: { error: unknown }) {
  return (
    <p role="alert" className="text-small text-danger not-empty:mt-4">
      {error ? errorMessage(error) : null}
    </p>
  );
}

/** "Saturn links (D03) · Resin · defekt" for the printer select. */
function printerOption(desk: PrinterDeskOut): string {
  const name = desk.name ? `${desk.name} (${desk.code})` : desk.code;
  const state = desk.status === "in_service" ? "" : ` · ${PRINTER_STATE_PHRASES[desk.status]}`;
  return `${name} · ${TECHNOLOGY_LABELS[desk.technology]}${state}`;
}

type PlannedLine = { part: PartOut; quantity: number };

type PlanJobDialogProps = {
  printers: readonly PrinterDeskOut[];
  /** The printer the dialog starts with, e.g. from its card. */
  printerId?: string;
  trigger: ReactNode;
};

/** Put a plate together for a printer: parts of its technology, how many, how long. */
export function PlanJobDialog({ printers, printerId, trigger }: PlanJobDialogProps) {
  const choosable = printers.filter((desk) => desk.status !== "retired");
  const [open, setOpen] = useState(false);
  const [chosen, setChosen] = useState(printerId ?? choosable[0]?.id ?? "");
  const [lines, setLines] = useState<PlannedLine[]>([]);
  const [search, setSearch] = useState("");
  const [duration, setDuration] = useState("");
  const [note, setNote] = useState("");
  const refresh = useManufacturingRefresh();
  const printer = choosable.find((desk) => desk.id === chosen);
  const query = useDeferredValue(search.trim());
  const candidates = useParts(
    { technology: printer?.technology, ...(query ? { q: query } : {}) },
    open && printer !== undefined,
  );
  const minutes = parseDuration(duration);
  const estimate = printer
    ? estimateMinutes(
        printer.technology,
        lines.map((line) => ({
          plateMinutes: line.part.plate_minutes,
          perPlate: line.part.parts_per_plate,
          quantity: line.quantity,
        })),
      )
    : null;
  const plan = useMutation<PrintJobOut, ApiProblem>({
    mutationFn: () =>
      createPrintJob({
        printer_id: chosen,
        lines: lines.map((line) => ({ part_id: line.part.id, quantity: line.quantity })),
        planned_minutes: minutes ?? null,
        note,
      }),
    onSuccess() {
      refresh();
      setOpen(false);
    },
  });

  const reset = () => {
    setChosen(printerId ?? choosable[0]?.id ?? "");
    setLines([]);
    setSearch("");
    setDuration("");
    setNote("");
    plan.reset();
  };
  const changePrinter = (id: string) => {
    const next = choosable.find((desk) => desk.id === id);
    // Parts of another technology cannot go on the new printer's plate.
    setLines((current) => current.filter((line) => line.part.technology === next?.technology));
    setChosen(id);
  };
  const add = (part: PartOut) =>
    setLines((current) =>
      current.some((line) => line.part.id === part.id) ? current : [...current, { part, quantity: 1 }],
    );
  const offered = (candidates.data ?? []).filter((part) => !lines.some((line) => line.part.id === part.id)).slice(0, 6);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) reset();
      }}
    >
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogTitle>Druckauftrag planen</DialogTitle>
        <DialogDescription>
          Eine Platte für einen Drucker: welche Teile, wie viele, wie lange. Sie wartet in seiner Warteschlange, bis
          jemand sie startet.
        </DialogDescription>
        {choosable.length === 0 ? (
          <p className="mt-6 text-small text-ink-secondary">Leg zuerst einen Drucker an.</p>
        ) : (
          <form
            className="mt-6 space-y-5"
            aria-label="Druckauftrag planen"
            onSubmit={(event) => {
              event.preventDefault();
              plan.mutate();
            }}
          >
            <FormField label="Drucker">
              {(field) => (
                <Select {...field} value={chosen} onChange={(event) => changePrinter(event.target.value)}>
                  {choosable.map((desk) => (
                    <option key={desk.id} value={desk.id}>
                      {printerOption(desk)}
                    </option>
                  ))}
                </Select>
              )}
            </FormField>

            <section aria-label="Teile auf der Platte" className="rounded-md border border-line">
              {lines.length === 0 ? (
                <p className="px-4 py-5 text-small text-ink-secondary">
                  Noch keine Teile. Such unten nach Teilenummer oder Name.
                </p>
              ) : (
                <ul className="divide-y divide-line">
                  {lines.map((line) => (
                    <li key={line.part.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
                      <span className="min-w-0 flex-1">
                        <span className="block font-mono text-hint text-ink-tertiary">{line.part.part_number}</span>
                        <span className="block truncate font-medium">{line.part.name}</span>
                      </span>
                      <QuantityStepper
                        value={line.quantity}
                        max={1000}
                        label={`Menge ${line.part.name}`}
                        onChange={(quantity) =>
                          setLines((current) =>
                            current.map((entry) => (entry.part.id === line.part.id ? { ...entry, quantity } : entry)),
                          )
                        }
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        aria-label={`${line.part.name} entfernen`}
                        onClick={() => setLines((current) => current.filter((entry) => entry.part.id !== line.part.id))}
                      >
                        Entfernen
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
              <div className="border-t border-line bg-sunken px-4 py-3">
                <Input
                  type="search"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder={`Teil suchen (${printer ? TECHNOLOGY_LABELS[printer.technology] : "…"})`}
                  aria-label="Teil suchen"
                />
                {candidates.isError ? (
                  <p role="alert" className="mt-2 text-hint text-danger">
                    {errorMessage(candidates.error)}
                  </p>
                ) : offered.length > 0 ? (
                  <ul className="mt-2 flex flex-wrap gap-2" aria-label="Passende Teile">
                    {offered.map((part) => (
                      <li key={part.id}>
                        <button
                          type="button"
                          onClick={() => add(part)}
                          className="inline-flex max-w-full items-center gap-2 rounded-full border border-line-strong bg-surface px-3 py-1.5 text-small transition-colors hover:border-ink"
                        >
                          <span aria-hidden="true" className="text-accent">
                            +
                          </span>
                          <span className="font-mono text-hint text-ink-tertiary">{part.scale_code}</span>
                          <span className="truncate">{part.name}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : candidates.isSuccess ? (
                  <p className="mt-2 text-hint text-ink-tertiary">
                    Kein passendes Teil. Teile legst du unter „Teile & Material“ an.
                  </p>
                ) : null}
              </div>
            </section>

            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                label="Druckdauer"
                hint={DURATION_HINT}
                error={minutes === undefined ? "Bitte z. B. 3:12 oder 192 eingeben." : undefined}
              >
                {(field) => (
                  <Input
                    {...field}
                    value={duration}
                    onChange={(event) => setDuration(event.target.value)}
                    inputMode="numeric"
                    placeholder={estimate !== null ? `≈ ${formatMinutes(estimate)}` : "z. B. 3:12"}
                    className="tabular-nums"
                  />
                )}
              </FormField>
              <FormField label="Notiz" hint="z. B. Farbe oder Ausrichtung">
                {(field) => (
                  <Textarea
                    {...field}
                    value={note}
                    onChange={(event) => setNote(event.target.value)}
                    rows={2}
                    className="min-h-12"
                  />
                )}
              </FormField>
            </div>
            {estimate !== null && duration.trim() === "" ? (
              <p className="text-hint text-ink-tertiary">Geschätzt aus den Druckdaten: {formatMinutes(estimate)}.</p>
            ) : null}
            <Failure error={plan.error} />
            <DialogActions onCancel={() => setOpen(false)}>
              <Button
                type="submit"
                size="sm"
                disabled={lines.length === 0 || minutes === undefined || plan.isPending}
                aria-busy={plan.isPending || undefined}
              >
                {plan.isPending ? "Plant …" : "In die Warteschlange"}
              </Button>
            </DialogActions>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

/** Report a plate done: how many of each part came out well (all, unless changed). */
export function CompleteJobDialog({ job, trigger }: { job: PrintJobOut; trigger: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [good, setGood] = useState<Record<string, number>>({});
  const refresh = useManufacturingRefresh();
  const complete = useMutation<PrintJobOut, ApiProblem>({
    mutationFn: () =>
      completePrintJob(job.id, {
        lines: job.lines.map((line) => ({ part_id: line.part.id, good: good[line.part.id] ?? line.quantity })),
      }),
    onSuccess() {
      refresh();
      setOpen(false);
    },
  });
  const goodTotal = job.lines.reduce((sum, line) => sum + (good[line.part.id] ?? line.quantity), 0);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          setGood({});
          complete.reset();
        }
      }}
    >
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogTitle>{jobTitle(job)} fertig melden</DialogTitle>
        <DialogDescription>Wie viele Teile sind gut geworden? Der Rest zählt als Ausschuss.</DialogDescription>
        <ul className="mt-6 divide-y divide-line rounded-md border border-line">
          {job.lines.map((line) => (
            <li key={line.part.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
              <span className="min-w-0">
                <span className="block font-mono text-hint text-ink-tertiary">{line.part.part_number}</span>
                <span className="block font-medium">{line.part.name}</span>
              </span>
              <span className="flex items-center gap-2 text-small text-ink-secondary">
                <QuantityStepper
                  value={good[line.part.id] ?? line.quantity}
                  min={0}
                  max={line.quantity}
                  label={`Gute Teile ${line.part.name}`}
                  onChange={(value) => setGood((current) => ({ ...current, [line.part.id]: value }))}
                />
                von {line.quantity}
              </span>
            </li>
          ))}
        </ul>
        <p className="mt-3 text-small text-ink-secondary">
          {goodTotal} von {job.part_count} Teilen gut
          {goodTotal < job.part_count ? `, ${job.part_count - goodTotal} Ausschuss` : ""}.
        </p>
        <Failure error={complete.error} />
        <DialogActions onCancel={() => setOpen(false)}>
          <Button
            type="button"
            size="sm"
            disabled={complete.isPending}
            aria-busy={complete.isPending || undefined}
            onClick={() => complete.mutate()}
          >
            {complete.isPending ? "Meldet …" : "Fertig melden"}
          </Button>
        </DialogActions>
      </DialogContent>
    </Dialog>
  );
}

const FAILURE_REASONS = [
  "Haftung verloren",
  "Stützen abgerissen",
  "Schichtversatz",
  "Folie / Düse",
  "Bruch beim Ablösen",
];

/** The whole plate is lost: why, in a word or two. */
export function FailJobDialog({ job, trigger }: { job: PrintJobOut; trigger: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const refresh = useManufacturingRefresh();
  const fail = useMutation<PrintJobOut, ApiProblem>({
    mutationFn: () => failPrintJob(job.id, { reason }),
    onSuccess() {
      refresh();
      setOpen(false);
    },
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          setReason("");
          fail.reset();
        }
      }}
    >
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogTitle>{jobTitle(job)} ist ein Fehldruck</DialogTitle>
        <DialogDescription>
          Alle {job.part_count} Teile der Platte zählen als Ausschuss. Der Drucker ist danach wieder frei.
        </DialogDescription>
        <ul className="mt-5 flex flex-wrap gap-2" aria-label="Häufige Gründe">
          {FAILURE_REASONS.map((text) => (
            <li key={text}>
              <button
                type="button"
                aria-pressed={reason === text}
                onClick={() => setReason(text)}
                className="rounded-full border border-line-strong px-3 py-1.5 text-small transition-colors hover:border-ink aria-pressed:border-selected aria-pressed:bg-selected aria-pressed:text-on-selected"
              >
                {text}
              </button>
            </li>
          ))}
        </ul>
        <FormField label="Grund" className="mt-4">
          {(field) => (
            <Input {...field} value={reason} onChange={(event) => setReason(event.target.value)} maxLength={200} />
          )}
        </FormField>
        <Failure error={fail.error} />
        <DialogActions onCancel={() => setOpen(false)}>
          <Button
            type="button"
            size="sm"
            variant="danger"
            disabled={fail.isPending}
            aria-busy={fail.isPending || undefined}
            onClick={() => fail.mutate()}
          >
            {fail.isPending ? "Bucht …" : "Als Fehldruck buchen"}
          </Button>
        </DialogActions>
      </DialogContent>
    </Dialog>
  );
}

type MoveJobDialogProps = {
  job: PrintJobOut;
  printers: readonly PrinterDeskOut[];
  trigger: ReactNode;
};

/** A waiting plate: to another printer of its technology, a new duration, or not at all. */
export function MoveJobDialog({ job, printers, trigger }: MoveJobDialogProps) {
  const fitting = printers.filter((desk) => desk.technology === job.technology && desk.status !== "retired");
  const [open, setOpen] = useState(false);
  const [printerId, setPrinterId] = useState(job.printer.id);
  const [duration, setDuration] = useState(job.planned_minutes === null ? "" : String(job.planned_minutes));
  const [note, setNote] = useState(job.note);
  const refresh = useManufacturingRefresh();
  const minutes = parseDuration(duration);
  const move = useMutation<PrintJobOut, ApiProblem>({
    mutationFn: () => planPrintJob(job.id, { printer_id: printerId, planned_minutes: minutes ?? null, note }),
    onSuccess() {
      refresh();
      setOpen(false);
    },
  });
  const cancel = useMutation<PrintJobOut, ApiProblem>({
    mutationFn: () => cancelPrintJob(job.id),
    onSuccess() {
      refresh();
      setOpen(false);
    },
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          setPrinterId(job.printer.id);
          setDuration(job.planned_minutes === null ? "" : String(job.planned_minutes));
          setNote(job.note);
          move.reset();
          cancel.reset();
        }
      }}
    >
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogTitle>{jobTitle(job)} planen</DialogTitle>
        <DialogDescription>
          Die Platte wartet noch. Sie kann auf einen anderen Drucker derselben Technik.
        </DialogDescription>
        <form
          className="mt-6 space-y-4"
          aria-label={`${jobTitle(job)} planen`}
          onSubmit={(event) => {
            event.preventDefault();
            move.mutate();
          }}
        >
          <FormField label="Drucker">
            {(field) => (
              <Select {...field} value={printerId} onChange={(event) => setPrinterId(event.target.value)}>
                {fitting.map((desk) => (
                  <option key={desk.id} value={desk.id}>
                    {printerOption(desk)}
                  </option>
                ))}
              </Select>
            )}
          </FormField>
          <FormField
            label="Druckdauer"
            hint={DURATION_HINT}
            error={minutes === undefined ? "Bitte z. B. 3:12 oder 192 eingeben." : undefined}
          >
            {(field) => (
              <Input
                {...field}
                value={duration}
                onChange={(event) => setDuration(event.target.value)}
                inputMode="numeric"
                className="tabular-nums"
              />
            )}
          </FormField>
          <FormField label="Notiz">
            {(field) => (
              <Input {...field} value={note} onChange={(event) => setNote(event.target.value)} maxLength={500} />
            )}
          </FormField>
          <Failure error={move.error ?? cancel.error} />
          <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="text-danger hover:bg-danger-subtle hover:text-danger"
              disabled={cancel.isPending}
              onClick={() => {
                if (window.confirm(`${jobTitle(job)} streichen? Die Platte wird nicht gedruckt.`)) {
                  cancel.mutate();
                }
              }}
            >
              Auftrag streichen
            </Button>
            <div className="flex gap-3">
              <Button type="button" variant="secondary" size="sm" onClick={() => setOpen(false)}>
                Abbrechen
              </Button>
              <Button
                type="submit"
                size="sm"
                disabled={minutes === undefined || move.isPending}
                aria-busy={move.isPending || undefined}
              >
                {move.isPending ? "Speichert …" : "Speichern"}
              </Button>
            </div>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
