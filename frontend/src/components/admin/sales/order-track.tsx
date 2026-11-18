"use client";

import { useQueryClient } from "@tanstack/react-query";
import type { Route } from "next";
import Link from "next/link";
import { useState } from "react";

import { ConnectionLamp } from "@/components/admin/connection-lamp";
import { useNow } from "@/components/admin/manufacturing/use-manufacturing";
import { Button } from "@/components/ui/button";
import { PendingNotice } from "@/components/ui/pending-notice";
import { getListToMakeQueryKey } from "@/lib/api/generated/admin-inventory/admin-inventory";
import { getListOrdersQueryKey, getListWithdrawalsQueryKey } from "@/lib/api/generated/admin-sales/admin-sales";
import type { OrderStatus, OrderSummaryOut, StaffRole } from "@/lib/api/generated/model";
import { errorMessage } from "@/lib/i18n/problems";
import { ADMIN_EVENTS_URL, ORDER_EVENT_TYPES, orderEventOf, withdrawalEventOf } from "@/lib/realtime/events";
import { useEventStream } from "@/lib/realtime/use-event-stream";
import { OFFICE_ROLES } from "@/lib/staff";
import { cn } from "@/lib/utils";

import { laneCount, orderAge, splitPaid, useOrderLane, useWaitingOrderIds } from "./use-order-lanes";

/** Pieces booked in or out change which paid orders still wait for the workshop. */
const TO_MAKE_EVENT_TYPES = ["inventory.stock.changed", "inventory.allocation.backordered"] as const;

/** How many of the latest shipped orders stand at the last station. */
const SHIPPED_SHOWN = 8;

type StationKey = "arrived" | "making" | "ready" | "shipped";

type Station = {
  key: StationKey;
  name: string;
  sub: string;
  count: string;
  wagons: readonly OrderSummaryOut[];
  empty: string;
  /** Where the station's button leads: a state of the list, or a page. */
  more: { label: string; list: OrderStatus } | { label: string; href: Route } | null;
};

type OrderTrackProps = {
  staffRole: StaffRole;
  onStreamClosed: () => void;
  /** Opens the list on one state ("Alle offenen", "Alle versendeten"). */
  onOpenList: (status: OrderStatus) => void;
};

/**
 * The Gleisbild (ADR 0030): every open order is a wagon on one line, standing at the
 * station its state puts it at: Eingang (not paid yet), Fertigung (paid, waits for a
 * piece from the workshop; owner and staff only), Versand (paid and complete) and
 * Unterwegs (the latest shipped ones). Wagons from eBay carry a terracotta edge. Live.
 */
export function OrderTrack({ staffRole, onStreamClosed, onOpenList }: OrderTrackProps) {
  const queryClient = useQueryClient();
  const office = OFFICE_ROLES.has(staffRole);
  const now = useNow(60_000);
  const [selected, setSelected] = useState<StationKey>("ready");

  const unpaid = useOrderLane("pending_payment");
  const paid = useOrderLane("paid");
  const shipped = useOrderLane("shipped", SHIPPED_SHOWN);
  const waiting = useWaitingOrderIds(office);
  const { ready, making } = splitPaid(paid.data?.items ?? [], waiting);

  const stream = useEventStream({
    url: ADMIN_EVENTS_URL,
    eventTypes: office ? [...ORDER_EVENT_TYPES, ...TO_MAKE_EVENT_TYPES] : ORDER_EVENT_TYPES,
    onMessage(data) {
      if (office) {
        void queryClient.invalidateQueries({ queryKey: getListToMakeQueryKey() });
      }
      if (withdrawalEventOf(data) !== null) {
        void queryClient.invalidateQueries({ queryKey: getListWithdrawalsQueryKey() });
        return;
      }
      if (orderEventOf(data) !== null) {
        void queryClient.invalidateQueries({ queryKey: getListOrdersQueryKey() });
      }
    },
    onClosed: onStreamClosed,
  });

  // Orders come newest first; a line is worked from its oldest wagon.
  const oldestFirst = (orders: readonly OrderSummaryOut[]) => [...orders].reverse();
  const stations: Station[] = [
    {
      key: "arrived",
      name: "Eingang",
      sub: "neu, noch unbezahlt",
      count: laneCount(unpaid.data),
      wagons: oldestFirst(unpaid.data?.items ?? []),
      empty: "Nichts wartet auf Geld.",
      more: { label: "Alle offenen", list: "pending_payment" },
    },
    ...(office
      ? [
          {
            key: "making" as const,
            name: "Fertigung",
            sub: "bezahlt, wartet auf Stücke",
            count: laneCount(paid.data, making.length),
            wagons: oldestFirst(making),
            empty: "Jede Bestellung hat ihre Stücke.",
            more: { label: "Zur Druckerhalle", href: "/admin/fertigung" as Route },
          },
        ]
      : []),
    {
      key: "ready",
      name: "Versand",
      sub: office ? "vollständig, kann raus" : "bezahlt, zu packen",
      count: laneCount(paid.data, ready.length),
      wagons: oldestFirst(ready),
      empty: "Gerade muss nichts raus.",
      more: { label: "Alle zu versendenden", list: "paid" },
    },
    {
      key: "shipped",
      name: "Unterwegs",
      sub: "zuletzt versendet",
      count: laneCount(shipped.data),
      wagons: shipped.data?.items ?? [],
      empty: "Noch nichts versendet.",
      more: { label: "Alle versendeten", list: "shipped" },
    },
  ];
  const queries = [unpaid, paid, shipped];
  const failed = queries.find((query) => query.isError);
  const open = (unpaid.data?.items.length ?? 0) + (paid.data?.items.length ?? 0);
  const columns = office ? "lg:grid-cols-4" : "lg:grid-cols-3";

  return (
    <section aria-label="Übersicht der Bestellungen">
      <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-4">
        <dl className="flex flex-wrap gap-x-7 gap-y-2 text-small">
          <Figure value={paid.isSuccess && unpaid.isSuccess ? String(open) : "–"} label="offen" />
          <Figure value={paid.isSuccess ? String(ready.length) : "–"} label="versandfertig" highlight />
        </dl>
        <ConnectionLamp state={stream.state} onReconnect={stream.reconnect} />
      </div>

      {failed ? (
        <p role="alert" className="mt-8 text-small text-danger">
          {errorMessage(failed.error)}
        </p>
      ) : queries.some((query) => query.isPending) ? (
        <PendingNotice className="mt-8">Die Übersicht wird geladen …</PendingNotice>
      ) : (
        <>
          {/* The line with its stations: on a desk only, where the columns stand side by side. */}
          <div className="relative mt-9 max-lg:hidden">
            <svg viewBox="0 0 1200 120" preserveAspectRatio="none" aria-hidden="true" className="block h-[7.5rem] w-full">
              <path d="M0 78H1200" stroke="var(--ink)" strokeWidth="4" vectorEffect="non-scaling-stroke" fill="none" />
              <path
                d="M0 78H1200"
                stroke="var(--canvas)"
                strokeWidth="1.5"
                strokeDasharray="2 14"
                vectorEffect="non-scaling-stroke"
                fill="none"
              />
              <path d="M0 24H40L110 78" stroke="var(--highlight)" strokeWidth="4" vectorEffect="non-scaling-stroke" fill="none" />
            </svg>
            <span className="absolute top-0 left-0 font-mono text-[0.6875rem] tracking-[0.1em] text-accent uppercase">
              Zufahrt eBay
            </span>
            <div className={cn("absolute inset-0 grid", columns)}>
              {stations.map((station) => (
                <button
                  key={station.key}
                  type="button"
                  aria-pressed={station.key === selected}
                  aria-label={`${station.name}: ${station.count}`}
                  onClick={() => setSelected(station.key)}
                  className="relative cursor-pointer"
                >
                  <span
                    className={cn(
                      "absolute bottom-[3.6875rem] left-1/2 -translate-x-1/2 font-display leading-none font-extrabold tabular-nums transition-[font-size,color] duration-200 motion-reduce:transition-none",
                      station.key === selected ? "text-[4rem] text-highlight" : "text-[2.5rem] text-ink",
                    )}
                  >
                    {station.count}
                  </span>
                  <span
                    className={cn(
                      // Centred on the line, which runs 42 px above the foot of the drawing.
                      "absolute bottom-[1.9375rem] left-1/2 block size-[1.375rem] -translate-x-1/2 border-4 border-ink transition-colors duration-200",
                      station.key === selected ? "bg-action" : "bg-canvas",
                    )}
                  />
                </button>
              ))}
            </div>
          </div>

          <div className={cn("mt-6 grid items-start gap-3.5 sm:grid-cols-2 lg:mt-0", columns)}>
            {stations.map((station) => (
              <StationColumn
                key={station.key}
                station={station}
                selected={station.key === selected}
                now={now}
                onOpenList={onOpenList}
              />
            ))}
          </div>
        </>
      )}
    </section>
  );
}

function Figure({ value, label, highlight = false }: { value: string; label: string; highlight?: boolean }) {
  return (
    <div className="flex items-baseline gap-2">
      <dd className={cn("font-display text-[1.875rem] leading-none font-extrabold tabular-nums", highlight && "text-highlight")}>
        {value}
      </dd>
      <dt>{label}</dt>
    </div>
  );
}

function StationColumn({
  station,
  selected,
  now,
  onOpenList,
}: {
  station: Station;
  selected: boolean;
  now: Date;
  onOpenList: (status: OrderStatus) => void;
}) {
  const headingId = `station-${station.key}`;
  const more = station.more;
  return (
    <section
      aria-labelledby={headingId}
      className={cn("px-3 pt-3.5 pb-3 transition-colors duration-200 lg:min-h-[26rem]", selected ? "bg-sunken" : "bg-surface")}
    >
      <h2 id={headingId} className="flex items-baseline justify-between gap-3 text-[1.25rem] leading-6">
        {station.name}
        {/* Below a desk there is no line above the columns: the count stands here. */}
        <span className="font-display tabular-nums lg:hidden">{station.count}</span>
      </h2>
      <p className="mt-1 min-h-7 label-caps text-ink-secondary">{station.sub}</p>
      {station.wagons.length === 0 ? (
        <p className="mt-2.5 border border-dashed border-line-strong px-3 py-6 text-center text-small text-ink-secondary">
          {station.empty}
        </p>
      ) : (
        <ul aria-label={`${station.name}, älteste zuerst`}>
          {station.wagons.map((order) => (
            <li key={order.id} className="mt-2.5">
              <Wagon order={order} now={now} />
            </li>
          ))}
        </ul>
      )}
      {more ? (
        <div className="mt-3">
          {"href" in more ? (
            <Button asChild size="sm" variant={selected ? "primary" : "secondary"} className={cn("w-full", !selected && "border-ink")}>
              <Link href={more.href}>{more.label}</Link>
            </Button>
          ) : (
            <Button
              type="button"
              size="sm"
              variant={selected ? "primary" : "secondary"}
              className={cn("w-full", !selected && "border-ink")}
              onClick={() => onOpenList(more.list)}
            >
              {more.label}
            </Button>
          )}
        </div>
      ) : null}
    </section>
  );
}

/** One order as a wagon: number, age, what is on it and for whom; two wheels below. */
function Wagon({ order, now }: { order: OrderSummaryOut; now: Date }) {
  const age = orderAge(order.placed_at, now);
  const ebay = order.channel === "ebay";
  return (
    <Link
      href={`/admin/bestellungen/${order.id}` as Route}
      className={cn(
        "block border-l-[5px] bg-canvas px-2.5 pt-2.5 pb-2 transition-[transform,box-shadow] duration-200 ease-out",
        "hover:-translate-[3px] hover:shadow-[6px_6px_0_var(--ink)] motion-reduce:transition-none motion-reduce:hover:translate-0",
        ebay ? "border-highlight" : "border-ink",
      )}
    >
      <span className="flex justify-between gap-2">
        <b className="font-mono text-hint font-medium">{order.number}</b>
        <time dateTime={order.placed_at} title={age.long} className="font-mono text-[0.6875rem] text-ink-secondary">
          {age.short}
        </time>
      </span>
      <span className="mt-1 block text-small leading-5 font-semibold">
        {order.item_count > 1 ? `${order.item_count} Stück · ` : ""}
        {order.first_line_title}
      </span>
      <span className="mt-0.5 block truncate text-hint text-ink-secondary">
        {order.recipient} · {ebay ? "eBay" : order.guest ? "Shop, Gast" : "Shop"}
      </span>
      <span aria-hidden="true" className="mt-2 flex gap-1">
        <span className="size-2.5 rounded-full bg-ink" />
        <span className="size-2.5 rounded-full bg-ink" />
      </span>
    </Link>
  );
}
