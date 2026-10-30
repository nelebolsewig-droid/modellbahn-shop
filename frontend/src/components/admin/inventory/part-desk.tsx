"use client";

import { useQueryClient } from "@tanstack/react-query";
import type { Route } from "next";
import Link from "next/link";

import { ConnectionLamp } from "@/components/admin/connection-lamp";
import { Panel } from "@/components/admin/panel";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { PendingNotice } from "@/components/ui/pending-notice";
import { StatusBadge, type StatusTone } from "@/components/ui/status-badge";
import { getGetPartStockQueryKey, useGetPartStock } from "@/lib/api/generated/admin-inventory/admin-inventory";
import type { PartDetailsOut, PartHistoryEntryOut, PartMovementReason, StaffRole } from "@/lib/api/generated/model";
import { PART_MOVEMENT_LABELS, partCount } from "@/lib/inventory/labels";
import { binLevel, partMovementText } from "@/lib/inventory/parts";
import { errorMessage } from "@/lib/i18n/problems";
import { TECHNOLOGY_LABELS } from "@/lib/manufacturing/hall";
import { ADMIN_EVENTS_URL, INVENTORY_EVENT_TYPES, stockEventOf } from "@/lib/realtime/events";
import { useEventStream } from "@/lib/realtime/use-event-stream";
import { cn } from "@/lib/utils";

import { MAY_MANAGE_STOCK } from "./inventory-overview";
import { PartBin } from "./part-bin";
import { CountPartsDialog, PartLabelDialog, WriteOffDialog } from "./part-dialogs";

const REASON_TONES: Readonly<Record<PartMovementReason, StatusTone>> = {
  receive: "success",
  assemble: "accent",
  count: "neutral",
  write_off: "danger",
  undo: "warning",
};

const moment = new Intl.DateTimeFormat("de-DE", {
  day: "2-digit",
  month: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

/** One printed part in the store: its boxes, what waits in receiving, and its journal. */
export function PartDesk({
  partNumber,
  staffRole,
  onStreamClosed,
}: {
  partNumber: string;
  staffRole: StaffRole;
  onStreamClosed: () => void;
}) {
  const queryClient = useQueryClient();
  const number = partNumber.toUpperCase();
  const details = useGetPartStock(number);
  const mayManage = MAY_MANAGE_STOCK.has(staffRole);
  const stream = useEventStream({
    url: ADMIN_EVENTS_URL,
    eventTypes: INVENTORY_EVENT_TYPES,
    onMessage(data) {
      const event = stockEventOf(data);
      if (event !== null && (event.partNumber === number || event.type === "inventory.parts.arrived")) {
        void queryClient.invalidateQueries({ queryKey: getGetPartStockQueryKey(number) });
      }
    },
    onClosed: onStreamClosed,
  });

  if (details.isPending) {
    return <PendingNotice>Das Teil wird geladen …</PendingNotice>;
  }
  if (details.isError) {
    return (
      <div className="space-y-4">
        <Alert tone="danger" title="Das Teil konnte nicht geladen werden">
          <p>{errorMessage(details.error)}</p>
        </Alert>
        <Button asChild variant="secondary">
          <Link href="/admin/lager">Zurück zum Lager</Link>
        </Button>
      </div>
    );
  }
  const { stock, receipts, history } = details.data;
  const { part } = stock;
  const fullest = Math.max(0, ...stock.places.map((place) => place.quantity));

  return (
    <>
      <nav aria-label="Lage im Lager" className="flex flex-wrap items-center gap-2 text-small text-ink-secondary">
        <Link href="/admin/lager" className="font-medium hover:text-ink">
          Lager
        </Link>
        <span aria-hidden="true">/</span>
        <span>Teile</span>
      </nav>

      <div className="mt-6 flex flex-wrap items-end justify-between gap-4">
        <div className="flex min-w-0 items-center gap-5">
          <span className="flex size-16 shrink-0 items-center justify-center rounded-md border border-line bg-surface">
            <PartBin level={binLevel(stock.total, Math.max(stock.total, 1))} className="w-12" />
          </span>
          <div className="min-w-0">
            <p className="label-caps text-ink-tertiary">
              Teil · {part.scale_code} · {TECHNOLOGY_LABELS[part.technology]}
              {part.active ? "" : " · archiviert"}
            </p>
            <h1 className="mt-1 font-mono text-heading tracking-wide break-all sm:text-title">{part.part_number}</h1>
            <p className="mt-1 text-small text-ink-secondary">{part.name}</p>
          </div>
        </div>
        <ConnectionLamp state={stream.state} onReconnect={stream.reconnect} />
      </div>

      <div className="mt-6 flex flex-wrap gap-2">
        <PartLabelDialog
          part={part}
          trigger={
            <Button type="button" size="sm">
              Etikett drucken
            </Button>
          }
        />
        {mayManage ? (
          <CountPartsDialog
            part={part}
            trigger={
              <Button type="button" size="sm" variant="secondary">
                Gezählt …
              </Button>
            }
          />
        ) : null}
      </div>

      <dl className="mt-8 grid grid-cols-3 gap-px overflow-hidden rounded-sm border border-line bg-line">
        <Tile label="In Boxen" value={stock.total} tone="text-success" />
        <Tile label="Im Wareneingang" value={stock.incoming} tone="text-warning" />
        <Tile label="Plätze" value={stock.places.length} tone="text-ink" />
      </dl>

      <div className="mt-6 grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_24rem]">
        <div className="space-y-6">
          <Panel title="Boxen" code="LG 21">
            {stock.places.length === 0 ? (
              <p className="text-small text-ink-secondary">
                In keiner Box. Teile aus dem Wareneingang kommen per Scan hinein: Box, dann dieses Etikett.
              </p>
            ) : (
              <ul className="divide-y divide-line border-y border-line">
                {stock.places.map((place) => (
                  <li
                    key={place.location_code}
                    className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-4 py-2.5"
                  >
                    <PartBin level={binLevel(place.quantity, fullest)} />
                    <div className="min-w-0">
                      <Link
                        href={`/admin/lager/plaetze/${place.location_code}` as Route}
                        className="font-mono text-small font-medium hover:underline"
                      >
                        {place.location_code}
                      </Link>
                      {place.location_name ? (
                        <p className="truncate text-hint text-ink-tertiary">{place.location_name}</p>
                      ) : null}
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-body-lg font-medium tabular-nums">{place.quantity}</span>
                      {mayManage ? (
                        <CountPartsDialog
                          part={part}
                          locationCode={place.location_code}
                          current={place.quantity}
                          trigger={
                            <Button
                              type="button"
                              size="sm"
                              variant="ghost"
                              aria-label={`${place.location_code} gezählt`}
                              className="px-3"
                            >
                              Zählen
                            </Button>
                          }
                        />
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
          {receipts.length > 0 ? <ReceivingList details={details.data} mayManage={mayManage} /> : null}
        </div>
        <Panel title="Journal" code="LG 23">
          {history.length === 0 ? (
            <p className="text-small text-ink-secondary">Noch nichts gebucht.</p>
          ) : (
            <ol className="relative space-y-4 border-l border-line pl-5">
              {history.map((entry) => (
                <JournalEntry key={entry.id} entry={entry} />
              ))}
            </ol>
          )}
        </Panel>
      </div>
    </>
  );
}

function Tile({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="bg-surface px-4 py-3">
      <dt className="label-caps text-ink-tertiary">{label}</dt>
      <dd
        className={cn("mt-1 text-[1.75rem] leading-9 font-light tabular-nums", value > 0 ? tone : "text-ink-disabled")}
      >
        {value}
      </dd>
    </div>
  );
}

function ReceivingList({ details, mayManage }: { details: PartDetailsOut; mayManage: boolean }) {
  return (
    <Panel title="Im Wareneingang" code="LG 22">
      <ul className="divide-y divide-line border-y border-line">
        {details.receipts.map((receipt) => (
          <li key={receipt.id} className="flex items-center justify-between gap-4 py-2.5">
            <p className="text-small">
              <span className="font-medium tabular-nums">{partCount(receipt.open)}</span>
              <span className="ml-2 text-ink-secondary">
                {receipt.print_job ? `aus Druck ${receipt.print_job.number} · ${receipt.print_job.printer_code}` : ""}
              </span>
            </p>
            {mayManage ? (
              <WriteOffDialog
                receipt={receipt}
                trigger={
                  <Button type="button" size="sm" variant="ghost" className="px-3 text-ink-secondary">
                    Ausbuchen
                  </Button>
                }
              />
            ) : null}
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function JournalEntry({ entry }: { entry: PartHistoryEntryOut }) {
  return (
    <li className="relative">
      <span
        aria-hidden="true"
        className="absolute top-1.5 -left-[1.6875rem] size-2.5 rounded-full border-2 border-surface bg-ink-tertiary"
      />
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <StatusBadge tone={REASON_TONES[entry.reason]}>{PART_MOVEMENT_LABELS[entry.reason]}</StatusBadge>
        <time className="font-mono text-hint text-ink-tertiary" dateTime={entry.occurred_at}>
          {moment.format(new Date(entry.occurred_at))}
        </time>
      </div>
      <p className="mt-1 text-small">{partMovementText(entry)}</p>
      {entry.note || entry.staff_name ? (
        <p className="mt-0.5 text-hint text-ink-tertiary">
          {entry.note ? `„${entry.note}“` : ""}
          {entry.note && entry.staff_name ? " · " : ""}
          {entry.staff_name ?? ""}
        </p>
      ) : null}
    </li>
  );
}
