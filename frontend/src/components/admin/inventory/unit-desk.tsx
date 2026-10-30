"use client";

import { useQueryClient } from "@tanstack/react-query";
import type { Route } from "next";
import Link from "next/link";
import { useState } from "react";

import { ConnectionLamp } from "@/components/admin/connection-lamp";
import { Panel } from "@/components/admin/panel";
import { FormError } from "@/components/forms/form-error";
import { SubmitButton } from "@/components/forms/submit-button";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { FormField } from "@/components/ui/form-field";
import { PendingNotice } from "@/components/ui/pending-notice";
import { StatusBadge } from "@/components/ui/status-badge";
import { Textarea } from "@/components/ui/textarea";
import {
  getGetUnitQueryKey,
  getListStockQueryKey,
  scrapUnit,
  useGetUnit,
} from "@/lib/api/generated/admin-inventory/admin-inventory";
import type { HistoryEntryOut, StaffRole, UnitDetailsOut } from "@/lib/api/generated/model";
import { useApiForm } from "@/lib/forms/use-api-form";
import { formatClock, formatLongDate } from "@/lib/format";
import { normalizeUnitCode } from "@/lib/inventory/codes";
import { MOVEMENT_LABELS, UNIT_STATUS_LABELS, UNIT_STATUS_TONES } from "@/lib/inventory/labels";
import { errorMessage } from "@/lib/i18n/problems";
import { ADMIN_EVENTS_URL, INVENTORY_EVENT_TYPES, stockEventOf } from "@/lib/realtime/events";
import { useEventStream } from "@/lib/realtime/use-event-stream";
import { cn } from "@/lib/utils";
import { scrapSchema } from "@/lib/validation/inventory";

import { MAY_MANAGE_STOCK } from "./inventory-overview";
import { LabelPrinter } from "./label-printer";
import { partHref } from "./parts-panels";

/** One piece: what it is, where it lies, and every step it took through the workshop. */
export function UnitDesk({ code: raw, staffRole, onStreamClosed }: { code: string; staffRole: StaffRole; onStreamClosed: () => void }) {
  const queryClient = useQueryClient();
  const code = normalizeUnitCode(decodeURIComponent(raw));
  const unit = useGetUnit(code);
  const stream = useEventStream({
    url: ADMIN_EVENTS_URL,
    eventTypes: INVENTORY_EVENT_TYPES,
    onMessage(data) {
      if (stockEventOf(data)?.unitCode === code) {
        void queryClient.invalidateQueries({ queryKey: getGetUnitQueryKey(code) });
      }
    },
    onClosed: onStreamClosed,
  });

  if (unit.isPending) {
    return <PendingNotice>Die Einheit wird geladen …</PendingNotice>;
  }
  if (unit.isError) {
    return (
      <div className="space-y-4">
        <Alert tone="danger" title="Die Einheit konnte nicht geladen werden">
          <p>{errorMessage(unit.error)}</p>
        </Alert>
        <Button asChild variant="secondary">
          <Link href="/admin/lager">Zurück zum Lager</Link>
        </Button>
      </div>
    );
  }
  const data = unit.data;
  const gone = data.status === "shipped" || data.status === "scrapped";

  return (
    <>
      <Link href="/admin/lager" className="inline-flex items-center gap-2 text-small font-medium text-ink-secondary hover:text-ink">
        <span aria-hidden="true">←</span> Lager
      </Link>
      <div className="mt-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <span className="label-caps text-ink-tertiary">Einheit</span>
            <StatusBadge tone={UNIT_STATUS_TONES[data.status]}>{UNIT_STATUS_LABELS[data.status]}</StatusBadge>
          </p>
          <h1 className="mt-3 font-mono text-heading tracking-wider sm:text-title">{data.display_code}</h1>
          <p className="mt-2 text-small text-ink-secondary">
            {data.variant?.title ?? "Gelöschter Artikel"}
            {data.variant ? <span className="ml-2 font-mono text-hint text-ink-tertiary">{data.variant.sku}</span> : null}
          </p>
        </div>
        <ConnectionLamp state={stream.state} onReconnect={stream.reconnect} />
      </div>

      <div className="mt-8 grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <Panel title="Lebenslauf" code="LG 21">
          <History entries={data.history} />
        </Panel>
        <div className="space-y-6">
          <Panel title="Steckbrief" code="LG 22">
            <Facts unit={data} />
          </Panel>
          {data.parts.length > 0 ? (
            <Panel title="Aus diesen Teilen" code="LG 25">
              <AssembledFrom unit={data} />
            </Panel>
          ) : null}
          {!gone ? (
            <Panel title="Etikett" code="LG 23">
              <p className="text-small text-ink-secondary">Abgerissen oder unlesbar? Gleicher Code, neues Etikett.</p>
              <ReprintDialog code={data.code} />
            </Panel>
          ) : null}
          {MAY_MANAGE_STOCK.has(staffRole) && !gone ? (
            <Panel title="Ausbuchen" code="LG 24">
              <ScrapUnit unit={data} />
            </Panel>
          ) : null}
        </div>
      </div>
    </>
  );
}

/** The parts the unit was assembled from, and the boxes they came out of. */
function AssembledFrom({ unit }: { unit: UnitDetailsOut }) {
  return (
    <ul className="divide-y divide-line border-y border-line text-small">
      {unit.parts.map((entry, index) => (
        <li key={index} className="grid grid-cols-[2.25rem_minmax(0,1fr)] gap-x-2 py-2">
          <span className="text-right tabular-nums">{entry.quantity} ×</span>
          <span className="min-w-0">
            {entry.part ? (
              <Link href={partHref(entry.part.part_number)} className="block truncate hover:underline">
                {entry.part.name}
              </Link>
            ) : (
              <span className="block">Unbekanntes Teil</span>
            )}
            <span className="block truncate font-mono text-hint text-ink-tertiary">
              {entry.location_code ? `aus ${entry.location_code}` : ""}
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
}

function Facts({ unit }: { unit: UnitDetailsOut }) {
  return (
    <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2.5 text-small">
      <dt className="text-ink-tertiary">Platz</dt>
      <dd>
        {unit.location ? (
          <Link href={`/admin/lager/plaetze/${unit.location.code}` as Route} className="font-mono text-accent hover:underline">
            {unit.location.code}
          </Link>
        ) : (
          "—"
        )}
        {unit.location?.name ? <span className="ml-2 text-ink-tertiary">{unit.location.name}</span> : null}
      </dd>
      <dt className="text-ink-tertiary">Bestellung</dt>
      <dd>
        {unit.order_id && unit.order_number ? (
          <Link href={`/admin/bestellungen/${unit.order_id}` as Route} className="font-mono text-accent hover:underline">
            {unit.order_number}
          </Link>
        ) : (
          "frei"
        )}
      </dd>
      {unit.variant?.gtin ? (
        <>
          <dt className="text-ink-tertiary">EAN</dt>
          <dd className="font-mono">{unit.variant.gtin}</dd>
        </>
      ) : null}
      <dt className="text-ink-tertiary">Erfasst</dt>
      <dd>{formatLongDate(new Date(unit.created_at))}</dd>
      {unit.scrap_note ? (
        <>
          <dt className="text-ink-tertiary">Grund</dt>
          <dd>„{unit.scrap_note}“</dd>
        </>
      ) : null}
    </dl>
  );
}

/** Every booking, oldest first, as stations on a line; reversals are struck through. */
function History({ entries }: { entries: readonly HistoryEntryOut[] }) {
  const reversed = new Set(entries.map((entry) => entry.reverses_id).filter((id): id is number => id !== null));
  return (
    <ol className="relative">
      {entries.map((entry, index) => {
        const undone = reversed.has(entry.id);
        const last = index === entries.length - 1;
        return (
          <li key={entry.id} className="relative grid grid-cols-[1.5rem_minmax(0,1fr)] gap-x-3 pb-5 last:pb-0">
            {!last ? <span aria-hidden="true" className="absolute top-5 bottom-0 left-[0.6875rem] w-0.5 bg-line-strong" /> : null}
            <span
              aria-hidden="true"
              className={cn(
                "relative mt-0.5 size-6 rounded-full border-2",
                last ? "border-selected bg-selected ring-4 ring-accent-subtle" : "border-selected bg-surface",
                entry.reverses_id !== null && "border-ink-tertiary",
              )}
            />
            <div className="min-w-0">
              <p className={cn("text-small font-medium", undone && "text-ink-tertiary line-through")}>
                {MOVEMENT_LABELS[entry.reason]}
                {undone ? <span className="sr-only"> (zurückgenommen)</span> : null}
              </p>
              <p className="mt-0.5 flex flex-wrap gap-x-3 text-hint text-ink-tertiary">
                <time dateTime={entry.occurred_at}>
                  {formatLongDate(new Date(entry.occurred_at))}, {formatClock(new Date(entry.occurred_at))}
                </time>
                {entry.staff_name ? <span>{entry.staff_name}</span> : null}
                {entry.scan_id ? <span>per Scan</span> : null}
              </p>
              {entry.from_location_code || entry.to_location_code ? (
                <p className="mt-1 font-mono text-hint text-ink-secondary">
                  {entry.from_location_code ?? "—"} → {entry.to_location_code ?? "—"}
                </p>
              ) : null}
              {entry.order_number ? <p className="mt-1 font-mono text-hint text-ink-secondary">{entry.order_number}</p> : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function ReprintDialog({ code }: { code: string }) {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button type="button" size="sm" variant="secondary" className="mt-4">
          Etikett nachdrucken
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogTitle>Etikett nachdrucken</DialogTitle>
        <DialogDescription>Der Code bleibt derselbe; das alte Etikett bitte entfernen.</DialogDescription>
        <LabelPrinter unitCodes={[code]} className="mt-6" />
      </DialogContent>
    </Dialog>
  );
}

function ScrapUnit({ unit }: { unit: UnitDetailsOut }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const { form, onSubmit, formError } = useApiForm({
    schema: scrapSchema,
    defaultValues: { note: "" },
    async submit(values) {
      const updated = await scrapUnit(unit.code, values);
      queryClient.setQueryData(getGetUnitQueryKey(unit.code), { ...unit, ...updated });
      void queryClient.invalidateQueries({ queryKey: getGetUnitQueryKey(unit.code) });
      void queryClient.invalidateQueries({ queryKey: getListStockQueryKey() });
      setOpen(false);
    },
  });
  const {
    register,
    formState: { errors, isSubmitting },
  } = form;
  return (
    <>
      <p className="text-small text-ink-secondary">
        Beschädigt, verloren oder als Muster verschenkt: Das Stück verlässt den Bestand.
        {unit.status === "allocated" || unit.status === "picked" ? " Die Bestellung bekommt dafür ein anderes Stück oder wartet auf die Fertigung." : ""}
      </p>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) {
            form.reset();
          }
        }}
      >
        <DialogTrigger asChild>
          <Button type="button" variant="secondary" size="sm" className="mt-4 border-danger text-danger hover:border-danger hover:bg-danger-subtle">
            Ausbuchen …
          </Button>
        </DialogTrigger>
        <DialogContent>
          <DialogTitle>{unit.display_code} ausbuchen?</DialogTitle>
          <DialogDescription>Das lässt sich nicht rückgängig machen.</DialogDescription>
          <form noValidate onSubmit={onSubmit} className="mt-6">
            <FormError message={formError?.message} />
            <FormField label="Grund" hint="Optional, z. B. „Gehäuse gebrochen“." error={errors.note?.message}>
              {(control) => <Textarea {...control} {...register("note")} maxLength={200} className="min-h-20" />}
            </FormField>
            <div className="mt-6 flex flex-wrap justify-end gap-3">
              <DialogClose asChild>
                <Button type="button" variant="secondary">
                  Behalten
                </Button>
              </DialogClose>
              <SubmitButton variant="danger" pending={isSubmitting} pendingLabel="Wird ausgebucht …">
                Ausbuchen
              </SubmitButton>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
