"use client";

import type { Route } from "next";
import Link from "next/link";

import { PendingNotice } from "@/components/ui/pending-notice";
import { useListToMake } from "@/lib/api/generated/admin-inventory/admin-inventory";
import type { ToMakeOut } from "@/lib/api/generated/model";
import { formatShortDate } from "@/lib/format";
import { errorMessage } from "@/lib/i18n/problems";

/**
 * How many pieces paid orders wait for, for the count beside "Bestellungen" in the menu
 * (owner and staff only); null while unknown. Checked again every minute.
 */
export function useToMakeCount(enabled: boolean): number | null {
  const toMake = useListToMake({
    query: { enabled, refetchInterval: 60_000, select: (data) => data.quantity },
  });
  return enabled ? (toMake.data ?? null) : null;
}

/**
 * Zu fertigen: one row per Ausführung that paid orders wait for, the longest waiting
 * first (ADR 0029). Booking pieces in on the model's page serves the oldest order; the
 * row shrinks and goes.
 */
export function ToMakeList() {
  const toMake = useListToMake();
  if (toMake.isPending) {
    return <PendingNotice>Wird geladen …</PendingNotice>;
  }
  if (toMake.isError) {
    return (
      <p role="alert" className="text-small text-danger">
        {errorMessage(toMake.error)}
      </p>
    );
  }
  if (toMake.data.items.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-line-strong px-5 py-10 text-center text-small text-ink-secondary">
        Gerade nichts zu fertigen: Jede bezahlte Bestellung hat ihre Stücke.
      </p>
    );
  }
  return (
    <>
      <p className="text-small text-ink-secondary">
        Fertig gebaut? Auf der Seite des Modells „Einbuchen“: Die Stücke gehen an die älteste Bestellung.
      </p>
      <ul aria-label="Zu fertigen, am längsten wartend zuerst" className="mt-4 divide-y divide-line border-y border-line">
        {toMake.data.items.map((row) => (
          <ToMakeRow key={row.variant_id} row={row} />
        ))}
      </ul>
    </>
  );
}

function ToMakeRow({ row }: { row: ToMakeOut }) {
  return (
    <li className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-6 gap-y-1 py-3 text-small md:grid-cols-[minmax(0,1fr)_6rem_minmax(0,14rem)_7rem] md:items-baseline">
      <span className="min-w-0">
        {row.product_id ? (
          <Link href={`/admin/modelle/${row.product_id}` as Route} className="font-medium hover:underline hover:underline-offset-4">
            {row.model}
          </Link>
        ) : (
          <span className="font-medium text-ink-tertiary">{row.model}</span>
        )}
        <span className="block text-ink-secondary">{row.finish}</span>
      </span>
      <span className="text-right font-medium tabular-nums md:text-left">{row.quantity} Stück</span>
      <span className="col-span-2 flex flex-wrap gap-x-3 gap-y-1 md:col-span-1">
        {row.orders.map((order) => (
          <Link
            key={order.order_id}
            href={`/admin/bestellungen/${order.order_id}` as Route}
            className="font-mono text-hint text-accent hover:underline hover:underline-offset-4"
          >
            {order.number}
            {order.quantity > 1 ? ` (${order.quantity})` : ""}
          </Link>
        ))}
      </span>
      <span className="col-span-2 text-hint text-ink-tertiary md:col-span-1">
        seit <time dateTime={row.oldest_at}>{formatShortDate(new Date(row.oldest_at))}</time>
      </span>
    </li>
  );
}
