"use client";

import type { Route } from "next";
import Link from "next/link";
import { useDeferredValue, useState } from "react";

import { Panel } from "@/components/admin/panel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PendingNotice } from "@/components/ui/pending-notice";
import { useListPartStock, useListReceiving } from "@/lib/api/generated/admin-inventory/admin-inventory";
import type { PartStockLineOut, ReceiptOut } from "@/lib/api/generated/model";
import { partCount } from "@/lib/inventory/labels";
import { binLevel, receivingSlips, type ReceivingSlip } from "@/lib/inventory/parts";
import { errorMessage } from "@/lib/i18n/problems";
import { sinceText } from "@/lib/manufacturing/hall";
import { cn } from "@/lib/utils";

import { PartBin } from "./part-bin";
import { PartLabelDialog, WriteOffDialog } from "./part-dialogs";

export function partHref(partNumber: string): Route {
  return `/admin/lager/teile/${encodeURIComponent(partNumber)}` as Route;
}

/**
 * "Wareneingang": the good parts of finished plates until they lie in a box. One
 * delivery note per plate; putting away is a scan of the box and then of the part's label.
 */
export function ReceivingPanel({ mayManage }: { mayManage: boolean }) {
  const receiving = useListReceiving();
  const slips = receivingSlips(receiving.data?.items ?? []);
  const waiting = slips.reduce((sum, slip) => sum + slip.open, 0);

  return (
    <Panel
      title={waiting > 0 ? `Wareneingang · ${partCount(waiting)}` : "Wareneingang"}
      code="LG 03"
      actions={
        slips.length > 0 ? (
          <Button asChild size="sm" variant="ghost" className="-mr-3">
            <Link href="/admin/scanner">Einlagern im Scanner</Link>
          </Button>
        ) : null
      }
    >
      {receiving.isPending ? <PendingNotice>Der Wareneingang wird geladen …</PendingNotice> : null}
      {receiving.isError ? <p className="text-small text-danger">{errorMessage(receiving.error)}</p> : null}
      {receiving.isSuccess && slips.length === 0 ? (
        <p className="flex items-center gap-3 text-small text-ink-secondary">
          <CheckMark />
          Alles eingelagert. Fertig gemeldete Platten landen hier, bis ihre Teile in einer Box liegen.
        </p>
      ) : null}
      {slips.length > 0 ? (
        <>
          <ol className="grid gap-4 sm:grid-cols-2">
            {slips.map((slip) => (
              <DeliveryNote key={slip.key} slip={slip} mayManage={mayManage} />
            ))}
          </ol>
          <p className="mt-4 text-hint text-ink-tertiary">
            So kommen sie in die Box: im Scanner unter „Einlagern“ die Box scannen, dann das Teileetikett.
          </p>
        </>
      ) : null}
    </Panel>
  );
}

function DeliveryNote({ slip, mayManage }: { slip: ReceivingSlip; mayManage: boolean }) {
  const since = slip.finishedAt ? sinceText(new Date(slip.finishedAt), new Date()) : null;
  return (
    <li
      aria-label={slip.number === null ? "Eingang" : `Druck ${slip.number}`}
      className="relative rounded-sm border border-line bg-canvas"
    >
      {/* The torn-off top of a delivery note. */}
      <span aria-hidden="true" className="absolute inset-x-3 -top-px border-t-2 border-dashed border-line-strong" />
      <header className="flex items-baseline justify-between gap-3 px-4 pt-3.5">
        <p className="label-caps text-ink-tertiary">
          {slip.number === null ? "Eingang" : `Druck ${slip.number}`}
          {slip.printerCode ? <span className="ml-2 font-mono normal-case">{slip.printerCode}</span> : null}
        </p>
        {since ? <p className="text-hint text-ink-tertiary">fertig {since.replace(/^seit /, "vor ")}</p> : null}
      </header>
      <ul className="mt-2 divide-y divide-line border-t border-line">
        {slip.receipts.map((receipt) => (
          <ReceiptLine key={receipt.id} receipt={receipt} mayManage={mayManage} />
        ))}
      </ul>
    </li>
  );
}

function ReceiptLine({ receipt, mayManage }: { receipt: ReceiptOut; mayManage: boolean }) {
  const part = receipt.part;
  return (
    <li className="grid grid-cols-[3rem_minmax(0,1fr)] gap-x-3 px-4 py-2.5">
      <span className="text-right text-body-lg leading-6 font-medium tabular-nums">{receipt.open}</span>
      <div className="min-w-0">
        <p className="truncate text-small">
          {part ? (
            <Link href={partHref(part.part_number)} className="hover:underline">
              {part.name}
            </Link>
          ) : (
            "Unbekanntes Teil"
          )}
        </p>
        <p className="truncate font-mono text-hint text-ink-tertiary">{part?.part_number}</p>
        <div className="-ml-2.5 flex flex-wrap">
          {part ? (
            <PartLabelDialog
              part={part}
              trigger={
                <Button type="button" variant="ghost" size="sm" className="h-8 px-2.5">
                  Etikett
                </Button>
              }
            />
          ) : null}
          {mayManage ? (
            <WriteOffDialog
              receipt={receipt}
              trigger={
                <Button type="button" variant="ghost" size="sm" className="h-8 px-2.5 text-ink-secondary">
                  Ausbuchen
                </Button>
              }
            />
          ) : null}
        </div>
      </div>
    </li>
  );
}

function CheckMark() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" className="size-5 shrink-0 text-success">
      <circle cx="10" cy="10" r="8.25" fill="none" stroke="currentColor" strokeWidth="1.2" />
      <path
        d="m6.5 10.25 2.25 2.25 4.75-5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function matches(line: PartStockLineOut, query: string): boolean {
  if (query === "") {
    return true;
  }
  const haystack = `${line.part.name} ${line.part.part_number} ${line.part.scale_code}`.toLowerCase();
  return haystack.includes(query.toLowerCase());
}

const PLACES_SHOWN = 4;

/** "Teilelager": every printed part with its boxes, live. */
export function PartStockPanel() {
  const stock = useListPartStock();
  const [search, setSearch] = useState("");
  const query = useDeferredValue(search.trim());
  const lines = stock.data?.items ?? [];
  const shown = lines.filter((line) => matches(line, query));
  const fullest = Math.max(0, ...lines.flatMap((line) => line.places.map((place) => place.quantity)));
  const total = lines.reduce((sum, line) => sum + line.total, 0);

  return (
    <Panel title="Teilelager" code="LG 04">
      {stock.isPending ? <PendingNotice>Das Teilelager wird geladen …</PendingNotice> : null}
      {stock.isError ? <p className="text-small text-danger">{errorMessage(stock.error)}</p> : null}
      {stock.isSuccess && lines.length === 0 ? (
        <p className="text-small text-ink-secondary">
          Noch keine Teile im Lager. Fertig gemeldete Platten kommen in den Wareneingang, von dort in die Boxen.
        </p>
      ) : null}
      {lines.length > 0 ? (
        <>
          <p className="flex flex-wrap items-baseline gap-x-2 text-small text-ink-secondary">
            <span className="text-[1.75rem] leading-9 font-light text-ink tabular-nums">{total}</span>
            Teile in Boxen, {lines.length === 1 ? "1 Teilenummer" : `${lines.length} Teilenummern`}
          </p>
          {lines.length > 5 ? (
            <div className="mt-4">
              <label htmlFor="part-search" className="sr-only">
                Teile durchsuchen
              </label>
              <Input
                id="part-search"
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Name oder Teilenummer"
                autoComplete="off"
              />
            </div>
          ) : null}
          <ul className="mt-4 divide-y divide-line border-y border-line">
            {shown.map((line) => (
              <PartStockRow key={line.part.part_id} line={line} fullest={fullest} />
            ))}
            {shown.length === 0 ? <li className="py-4 text-small text-ink-secondary">Nichts gefunden.</li> : null}
          </ul>
        </>
      ) : null}
    </Panel>
  );
}

function PartStockRow({ line, fullest }: { line: PartStockLineOut; fullest: number }) {
  const { part } = line;
  const largest = Math.max(0, ...line.places.map((place) => place.quantity));
  return (
    <li className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1.5 py-3">
      <PartBin level={binLevel(largest, fullest)} />
      <div className="min-w-0">
        <Link href={partHref(part.part_number)} className="block truncate text-small font-medium hover:underline">
          {part.name}
        </Link>
        <p className="truncate font-mono text-hint text-ink-tertiary">
          {part.part_number}
          <span className="ml-2 font-sans">{part.scale_code}</span>
        </p>
      </div>
      <p className="text-right">
        <span className={cn("block text-body-lg font-medium tabular-nums", line.total === 0 && "text-ink-disabled")}>
          {line.total}
        </span>
        {line.incoming > 0 ? (
          <span className="block text-hint whitespace-nowrap text-warning">+{line.incoming} im Eingang</span>
        ) : (
          <span className="block text-hint text-ink-tertiary">in Boxen</span>
        )}
      </p>
      {line.places.length > 0 ? (
        <ul
          className="col-span-3 flex flex-wrap gap-1.5 sm:col-start-2 sm:col-end-4"
          aria-label={`Plätze ${part.name}`}
        >
          {line.places.slice(0, PLACES_SHOWN).map((place) => (
            <li key={place.location_code}>
              <Link
                href={`/admin/lager/plaetze/${place.location_code}` as Route}
                className="inline-flex items-baseline gap-1.5 rounded-xs bg-sunken px-2 py-0.5 font-mono text-hint hover:bg-line"
              >
                {place.location_code}
                <span className="tabular-nums text-ink-secondary">{place.quantity}</span>
              </Link>
            </li>
          ))}
          {line.places.length > PLACES_SHOWN ? (
            <li className="px-1 text-hint text-ink-tertiary">+ {line.places.length - PLACES_SHOWN}</li>
          ) : null}
        </ul>
      ) : null}
    </li>
  );
}
