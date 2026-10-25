import type { Route } from "next";
import Link from "next/link";

import { ResponsivePicture } from "@/components/ui/responsive-picture";
import type { AddressOut, OrderLineOut, OrderOut } from "@/lib/api/generated/model";
import { formatPrice } from "@/lib/catalog/format";
import { formatLongDate, formatTime } from "@/lib/format";
import { cn } from "@/lib/utils";

/*
 * The pieces every view of an order shares: the shop's status page, the customer's
 * order history and the admin area.
 */

type Station = { label: string; at: string | null };

/**
 * The order's way as a timetable line: placed, paid, shipped. Reached stations are
 * filled, the line between them drawn; a cancelled order ends in its own station.
 */
export function OrderTimeline({ order, className }: { order: OrderOut; className?: string }) {
  const stations: Station[] =
    order.status === "cancelled"
      ? [
          { label: "Bestellt", at: order.placed_at },
          ...(order.paid_at ? [{ label: "Bezahlt", at: order.paid_at }] : []),
          { label: "Storniert", at: order.cancelled_at },
        ]
      : [
          { label: "Bestellt", at: order.placed_at },
          { label: "Bezahlt", at: order.paid_at },
          { label: "Versendet", at: order.shipped_at },
        ];
  const reached = stations.filter((station) => station.at !== null).length;

  return (
    <ol aria-label="Verlauf der Bestellung" className={cn("grid", className)} style={{ gridTemplateColumns: `repeat(${stations.length}, minmax(0, 1fr))` }}>
      {stations.map((station, index) => {
        const done = station.at !== null;
        const cancelled = order.status === "cancelled" && index === stations.length - 1;
        return (
          <li key={station.label} className="relative pt-7">
            {/* The track to the next station. */}
            {index < stations.length - 1 ? (
              <span
                aria-hidden="true"
                className={cn(
                  "absolute top-[0.6875rem] left-3 h-0.5 w-full",
                  index + 1 < reached ? "bg-selected" : "bg-line-strong",
                )}
              />
            ) : null}
            <span
              aria-hidden="true"
              className={cn(
                "absolute top-1 left-0 size-6 rounded-full border-2",
                done ? (cancelled ? "border-ink-secondary bg-ink-secondary" : "border-selected bg-selected") : "border-line-strong bg-canvas",
                done && index === reached - 1 && !cancelled && order.status !== "shipped" && "ring-4 ring-accent-subtle",
              )}
            />
            <p className={cn("text-small font-medium", !done && "text-ink-tertiary")}>
              {station.label}
              <span className="sr-only">{done ? "" : " (noch nicht)"}</span>
            </p>
            {station.at ? (
              <p className="mt-0.5 text-hint text-ink-tertiary">
                <time dateTime={station.at}>
                  {formatLongDate(new Date(station.at))}, {formatTime(new Date(station.at))}
                </time>
              </p>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

/** The ordered articles with photo, quantity and price as they were bought. */
export function OrderLines({ lines, linkToProducts = true }: { lines: readonly OrderLineOut[]; linkToProducts?: boolean }) {
  return (
    <ul className="divide-y divide-line border-y border-line">
      {lines.map((line) => (
        <li key={`${line.variant_id}-${line.sku}`} className="grid grid-cols-[4.5rem_minmax(0,1fr)_auto] items-center gap-5 py-4">
          <span className="relative aspect-square rounded-md bg-stage p-1.5">
            {line.image ? <ResponsivePicture image={line.image} alt="" sizes="72px" variant="thumb" /> : null}
          </span>
          <span className="min-w-0">
            <span className="block font-medium">
              {linkToProducts ? (
                <Link href={`/produkte/${line.product_slug}` as Route} className="hover:underline hover:underline-offset-4">
                  {line.title}
                </Link>
              ) : (
                line.title
              )}
            </span>
            <span className="mt-1 block text-hint text-ink-tertiary">
              <span className="font-mono">{line.sku}</span> · {line.quantity} × {formatPrice(line.unit_price_cents)}
            </span>
          </span>
          <span className="tabular-nums">{formatPrice(line.line_total_cents)}</span>
        </li>
      ))}
    </ul>
  );
}

/** A postal address as printed on the parcel. */
export function PostalAddress({ address, className }: { address: AddressOut; className?: string }) {
  return (
    <address className={cn("text-small not-italic", className)}>
      {address.recipient}
      <br />
      {address.street}
      <br />
      {address.postal_code} {address.city}
      <br />
      {address.country_name}
    </address>
  );
}
