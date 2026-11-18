"use client";

import type { Route } from "next";
import Link from "next/link";
import { useState } from "react";

import {
  CountDialog,
  ModelLabelsDialog,
  MoveStockDialog,
  ScrapStockDialog,
  type CountRow,
  type StockVariant,
} from "@/components/admin/inventory/stock-dialogs";
import { UnitsDialog } from "@/components/admin/inventory/units-dialog";
import { Panel } from "@/components/admin/panel";
import { Button } from "@/components/ui/button";
import { ColorDot } from "@/components/ui/color-dot";
import { PendingNotice } from "@/components/ui/pending-notice";
import { useGetStockHistory, useListPlaceStock, useListStock } from "@/lib/api/generated/admin-inventory/admin-inventory";
import type { PlaceStockOut, ProductOut, ReferencesOut, StockHistoryRowOut } from "@/lib/api/generated/model";
import { finishLabel } from "@/lib/catalog/format";
import { formatEventTime } from "@/lib/format";
import { MOVEMENT_LABELS } from "@/lib/inventory/labels";
import { lying } from "@/lib/inventory/stock";
import { errorMessage } from "@/lib/i18n/problems";

/** The model's Ausführungen in the order of its scales, named for people. */
export function modelVariants(product: ProductOut, references: ReferencesOut) {
  const finishName = (code: string) => references.finishes.find((finish) => finish.code === code)?.name ?? code;
  return product.scales.flatMap((scale) =>
    scale.variants.map((variant) => {
      const name = `${scale.scale_code} · ${finishLabel(finishName(variant.finish_code), variant.color)}`;
      return { variant, name, ref: { variantId: variant.id, title: `${product.name} · ${name}`, sku: variant.sku } satisfies StockVariant };
    }),
  );
}

/**
 * Bestand: every Ausführung with the places its pieces lie in, free and reserved, and
 * what can be done there: book in, take out, move, print labels, count.
 */
export function ModelStock({ product, references }: { product: ProductOut; references: ReferencesOut }) {
  const [message, setMessage] = useState("");
  const places = useListPlaceStock({ product_id: product.id });
  const stock = useListStock();
  const variants = modelVariants(product, references);
  const lines = places.data?.items ?? [];
  const totals = new Map((stock.data?.items ?? []).map((line) => [line.variant_id, line]));
  const names = new Map(variants.map((entry) => [entry.variant.id, entry.name]));
  const rows: CountRow[] = lines.map((line) => ({
    variantId: line.variant_id,
    locationCode: line.location.code,
    expected: lying(line),
    counted: lying(line),
    label: `${names.get(line.variant_id) ?? line.variant?.title ?? ""} · ${line.place}`,
  }));

  return (
    <Panel
      title="Bestand"
     
      actions={
        lines.length > 0 ? (
          <CountDialog
            title={product.name}
            rows={rows}
            onDone={setMessage}
            trigger={
              <Button type="button" size="sm" variant="secondary">
                Zählen
              </Button>
            }
          />
        ) : null
      }
    >
      <p role="status" className="text-small font-medium text-success empty:hidden">
        {message}
      </p>
      {places.isPending ? <PendingNotice>Der Bestand wird geladen …</PendingNotice> : null}
      {places.isError ? <p className="text-small text-danger">{errorMessage(places.error)}</p> : null}
      {variants.length === 0 ? (
        <p className="text-small text-ink-secondary">Noch keine Ausführung, also auch keine Stücke.</p>
      ) : null}
      <ul className="divide-y divide-line">
        {variants.map(({ variant, name, ref }) => {
          const here = lines.filter((line) => line.variant_id === variant.id);
          const free = here.reduce((sum, line) => sum + line.free, 0);
          const reserved = here.reduce((sum, line) => sum + line.reserved, 0);
          const total = totals.get(variant.id);
          return (
            <li key={variant.id} className="py-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="flex items-center gap-2 font-medium">
                    {variant.color !== "" ? <ColorDot color={variant.color} size="sm" /> : null}
                    <span className="min-w-0 truncate">{name}</span>
                  </p>
                  <p className="font-mono text-hint text-ink-tertiary">{variant.sku}</p>
                  <p className="mt-1 text-small tabular-nums">
                    <span className={free === 0 ? "text-ink-tertiary" : "font-medium"}>{free} frei</span>
                    {reserved > 0 ? ` · ${reserved} reserviert` : ""}
                    {total && total.backordered > 0 ? <span className="text-warning"> · {total.backordered} bestellt, warten</span> : null}
                    {total && total.labeled > 0 ? <span className="text-warning"> · {total.labeled} unverbucht</span> : null}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <UnitsDialog
                    variant={ref}
                    trigger={
                      <Button type="button" size="sm">
                        Einbuchen
                      </Button>
                    }
                  />
                  <ScrapStockDialog
                    variant={ref}
                    location={null}
                    free={free}
                    onDone={setMessage}
                    trigger={
                      <Button type="button" size="sm" variant="secondary" disabled={free === 0}>
                        Ausbuchen
                      </Button>
                    }
                  />
                  <ModelLabelsDialog
                    variant={ref}
                    quantity={free + reserved}
                    trigger={
                      <Button type="button" size="sm" variant="ghost">
                        Etiketten
                      </Button>
                    }
                  />
                </div>
              </div>
              {here.length > 0 ? (
                <ul className="mt-3 divide-y divide-line rounded-sm border border-line">
                  {here.map((line) => (
                    <PlaceRow key={line.location.id} line={line} variant={ref} onDone={setMessage} />
                  ))}
                </ul>
              ) : null}
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

function PlaceRow({ line, variant, onDone }: { line: PlaceStockOut; variant: StockVariant; onDone: (message: string) => void }) {
  const place = { code: line.location.code, place: line.place };
  return (
    <li className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-3 py-2">
      <Link href={`/admin/lager/plaetze/${line.location.code}` as Route} className="min-w-0 truncate text-small hover:underline">
        {line.place}
        {line.place !== line.location.code ? <span className="ml-2 font-mono text-hint text-ink-tertiary">{line.location.code}</span> : null}
      </Link>
      <span className="flex items-center gap-3">
        <span className="text-small tabular-nums">
          {line.free} frei{line.reserved > 0 ? ` · ${line.reserved} reserviert` : ""}
        </span>
        <MoveStockDialog
          variant={variant}
          from={place}
          available={lying(line)}
          onDone={onDone}
          trigger={
            <Button type="button" size="sm" variant="ghost">
              Umlagern
            </Button>
          }
        />
        <ScrapStockDialog
          variant={variant}
          location={place}
          free={line.free}
          onDone={onDone}
          trigger={
            <Button type="button" size="sm" variant="ghost" disabled={line.free === 0}>
              Ausbuchen
            </Button>
          }
        />
      </span>
    </li>
  );
}

/** `+3`, `−2` or `2`: what a booking did to the stock, as a number. */
export function signed(row: Pick<StockHistoryRowOut, "quantity" | "from_location" | "to_location">): string {
  if (row.to_location !== null && row.from_location === null) {
    return `+${row.quantity}`;
  }
  if (row.from_location !== null && row.to_location === null) {
    return `−${row.quantity}`;
  }
  return String(row.quantity);
}

function where(row: StockHistoryRowOut): string {
  if (row.from_place && row.to_place) {
    return `${row.from_place} → ${row.to_place}`;
  }
  return row.to_place ?? row.from_place ?? "";
}

/** Verlauf: the model's latest bookings, grouped per booking, newest first. */
export function ModelHistory({ productId }: { productId: string }) {
  const history = useGetStockHistory({ product_id: productId });
  // Labelling belongs to the booking-in right after it; it says nothing of its own.
  const rows = (history.data?.items ?? []).filter((row) => row.reason !== "label");
  return (
    <Panel title="Verlauf">
      {history.isPending ? <PendingNotice>Der Verlauf wird geladen …</PendingNotice> : null}
      {history.isError ? <p className="text-small text-danger">{errorMessage(history.error)}</p> : null}
      {history.isSuccess && rows.length === 0 ? <p className="text-small text-ink-secondary">Noch nichts gebucht.</p> : null}
      {rows.length > 0 ? (
        <ol className="divide-y divide-line">
          {rows.map((row, index) => (
            <li key={`${row.occurred_at}-${index}`} className="grid grid-cols-[3.5rem_minmax(0,1fr)_auto] items-baseline gap-3 py-2.5">
              <span className="text-right font-mono text-small font-medium tabular-nums">{signed(row)}</span>
              <span className="min-w-0">
                <span className="block text-small">
                  {MOVEMENT_LABELS[row.reason]}
                  {where(row) ? <span className="text-ink-secondary"> · {where(row)}</span> : null}
                </span>
                <span className="block truncate text-hint text-ink-tertiary">
                  {row.variant?.sku ?? ""}
                  {row.staff_name ? ` · ${row.staff_name}` : ""}
                  {row.scan ? " · per Scan" : ""}
                </span>
              </span>
              <time dateTime={row.occurred_at} className="text-hint text-ink-tertiary tabular-nums">
                {formatEventTime(new Date(row.occurred_at))}
              </time>
            </li>
          ))}
        </ol>
      ) : null}
    </Panel>
  );
}
