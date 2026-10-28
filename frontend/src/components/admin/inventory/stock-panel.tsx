"use client";

import { useDeferredValue, useState } from "react";

import { Panel } from "@/components/admin/panel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PendingNotice } from "@/components/ui/pending-notice";
import { useListStock } from "@/lib/api/generated/admin-inventory/admin-inventory";
import type { StockLineOut } from "@/lib/api/generated/model";
import { errorMessage } from "@/lib/i18n/problems";
import { cn } from "@/lib/utils";

import { UnitsDialog } from "./units-dialog";

type Part = { key: keyof Pick<StockLineOut, "in_stock" | "allocated" | "picked" | "labeled" | "backordered">; label: string; bar: string };

/** The states of a piece in the order of its way through the workshop. */
const PARTS: readonly Part[] = [
  { key: "in_stock", label: "Frei", bar: "bg-success" },
  { key: "allocated", label: "Reserviert", bar: "bg-accent" },
  { key: "picked", label: "Kommissioniert", bar: "bg-ink-secondary" },
  { key: "labeled", label: "Unverbucht", bar: "border border-warning bg-warning-subtle" },
  { key: "backordered", label: "In Fertigung", bar: "bg-warning" },
];

function matches(line: StockLineOut, query: string): boolean {
  if (query === "") {
    return true;
  }
  const variant = line.variant;
  const haystack = [variant?.title, variant?.sku, variant?.gtin].filter(Boolean).join(" ").toLowerCase();
  return haystack.includes(query.toLowerCase());
}

/** Stock per article, live: what is free, promised, packed, waiting or still to make. */
export function StockPanel() {
  const stock = useListStock();
  const [search, setSearch] = useState("");
  const query = useDeferredValue(search.trim());
  const lines = stock.data?.items ?? [];
  const shown = lines.filter((line) => matches(line, query));

  return (
    <Panel title="Bestand" code="LG 01">
      {stock.isPending ? <PendingNotice>Der Bestand wird geladen …</PendingNotice> : null}
      {stock.isError ? <p className="text-small text-danger">{errorMessage(stock.error)}</p> : null}
      {stock.isSuccess ? (
        <>
          <Totals lines={lines} />
          {lines.length > 0 ? (
            <div className="mt-6">
              <label htmlFor="stock-search" className="sr-only">
                Bestand durchsuchen
              </label>
              <Input
                id="stock-search"
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Name, Artikelnummer oder EAN"
                autoComplete="off"
              />
            </div>
          ) : null}
          {lines.length === 0 ? (
            <p className="mt-6 text-small text-ink-secondary">
              Noch nichts im Lager. „Einheiten erfassen“ legt die ersten Stücke mit Etikett an.
            </p>
          ) : (
            <ul className="mt-4 divide-y divide-line border-y border-line">
              {shown.map((line) => (
                <StockRow key={line.variant_id} line={line} />
              ))}
              {shown.length === 0 ? <li className="py-4 text-small text-ink-secondary">Nichts gefunden.</li> : null}
            </ul>
          )}
          <Legend className="mt-4" />
        </>
      ) : null}
    </Panel>
  );
}

function Totals({ lines }: { lines: readonly StockLineOut[] }) {
  const sum = (key: Part["key"]) => lines.reduce((total, line) => total + line[key], 0);
  const tiles = [
    { label: "Frei verkäuflich", value: sum("in_stock"), tone: "text-success" },
    { label: "Für Bestellungen", value: sum("allocated") + sum("picked"), tone: "text-accent" },
    { label: "Noch einzulagern", value: sum("labeled"), tone: "text-warning" },
    { label: "In Fertigung", value: sum("backordered"), tone: "text-warning" },
  ];
  return (
    <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-sm border border-line bg-line sm:grid-cols-4">
      {tiles.map((tile) => (
        <div key={tile.label} className="bg-surface px-4 py-3">
          <dt className="label-caps text-ink-tertiary">{tile.label}</dt>
          <dd className={cn("mt-1 text-[1.75rem] leading-9 font-light tabular-nums", tile.value > 0 ? tile.tone : "text-ink-disabled")}>
            {tile.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function StockRow({ line }: { line: StockLineOut }) {
  const variant = line.variant;
  const total = PARTS.reduce((sum, part) => sum + line[part.key], 0);
  const title = variant?.title ?? "Gelöschter Artikel";
  return (
    <li className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-2 py-3">
      <div className="min-w-0">
        <p className="truncate text-small font-medium">
          {title}
          {variant?.allow_backorder ? (
            <span className="ml-2 align-middle text-hint font-normal text-ink-tertiary">auf Bestellung</span>
          ) : null}
        </p>
        <p className="mt-0.5 flex flex-wrap gap-x-3 font-mono text-hint text-ink-tertiary">
          <span>{variant?.sku ?? line.variant_id}</span>
          {variant?.gtin ? <span>EAN {variant.gtin}</span> : null}
        </p>
      </div>
      <div className="flex items-center gap-3">
        <p className="text-right">
          <span className={cn("block text-body-lg font-medium tabular-nums", line.in_stock === 0 && "text-ink-disabled")}>
            {line.in_stock}
          </span>
          <span className="block text-hint text-ink-tertiary">frei</span>
        </p>
        {variant ? (
          <UnitsDialog
            variant={{ variantId: variant.variant_id, title: variant.title, sku: variant.sku }}
            trigger={
              <Button type="button" size="sm" variant="ghost" aria-label={`Einheiten erfassen: ${title}`}>
                + Stück
              </Button>
            }
          />
        ) : null}
      </div>
      {total > 0 ? (
        <div className="col-span-2">
          <div aria-hidden="true" className="flex h-1.5 gap-px overflow-hidden rounded-full bg-sunken">
            {PARTS.filter((part) => line[part.key] > 0).map((part) => (
              <span key={part.key} className={cn("h-full", part.bar)} style={{ flexGrow: line[part.key] }} />
            ))}
          </div>
          <p className="sr-only">
            {PARTS.filter((part) => line[part.key] > 0)
              .map((part) => `${part.label}: ${line[part.key]}`)
              .join(", ")}
          </p>
          <p aria-hidden="true" className="mt-1.5 flex flex-wrap gap-x-3 text-hint text-ink-tertiary">
            {PARTS.filter((part) => part.key !== "in_stock" && line[part.key] > 0).map((part) => (
              <span key={part.key}>
                {part.label} <span className="tabular-nums text-ink-secondary">{line[part.key]}</span>
              </span>
            ))}
          </p>
        </div>
      ) : null}
    </li>
  );
}

function Legend({ className }: { className?: string }) {
  return (
    <ul aria-hidden="true" className={cn("flex flex-wrap gap-x-4 gap-y-1 text-hint text-ink-tertiary", className)}>
      {PARTS.map((part) => (
        <li key={part.key} className="flex items-center gap-1.5">
          <span className={cn("inline-block h-1.5 w-4 rounded-full", part.bar)} />
          {part.label}
        </li>
      ))}
    </ul>
  );
}
