"use client";

import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import type { Route } from "next";
import Link from "next/link";
import { useState, type FormEvent } from "react";

import { ConnectionLamp } from "@/components/admin/connection-lamp";
import { Panel } from "@/components/admin/panel";
import { ChannelBadge } from "@/components/admin/sales/channel-badge";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { OptionGroup, OptionPill } from "@/components/ui/option-pill";
import { PendingNotice } from "@/components/ui/pending-notice";
import { SignalLamp } from "@/components/ui/signal-lamp";
import { StatusBadge } from "@/components/ui/status-badge";
import { getListOrdersQueryKey, listOrders } from "@/lib/api/generated/admin-sales/admin-sales";
import type { OrderPageOut, OrderStatus, OrderSummaryOut } from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";
import { formatPrice } from "@/lib/catalog/format";
import { formatEventTime } from "@/lib/format";
import { errorMessage } from "@/lib/i18n/problems";
import { ADMIN_EVENTS_URL, ORDER_EVENT_TYPES, orderEventOf } from "@/lib/realtime/events";
import { useEventStream } from "@/lib/realtime/use-event-stream";
import { ORDER_STATUS_LABELS, ORDER_STATUS_TONES } from "@/lib/sales/labels";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 50;

type StatusFilter = OrderStatus | "all";

const FILTERS: readonly { value: StatusFilter; label: string }[] = [
  { value: "all", label: "Alle" },
  { value: "paid", label: "Zu versenden" },
  { value: "pending_payment", label: "Zahlung offen" },
  { value: "shipped", label: "Versendet" },
  { value: "cancelled", label: "Storniert" },
];

/** Every order, newest first: filter by state, search by number or e-mail, live updates. */
export function OrderList({ onStreamClosed }: { onStreamClosed: () => void }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<StatusFilter>("all");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  // Orders placed while the page is open get a lamp until someone opens them.
  const [arrived, setArrived] = useState<ReadonlySet<string>>(new Set());

  const orders = useInfiniteQuery<OrderPageOut, ApiProblem>({
    queryKey: [...getListOrdersQueryKey(), "pages", { status, query }],
    queryFn: ({ pageParam, signal }) =>
      listOrders(
        {
          limit: PAGE_SIZE,
          ...(status !== "all" && { status: [status] }),
          ...(query && { q: query }),
          ...(typeof pageParam === "string" && { cursor: pageParam }),
        },
        { signal },
      ),
    initialPageParam: null,
    getNextPageParam: (page) => page.next_cursor,
  });
  const stream = useEventStream({
    url: ADMIN_EVENTS_URL,
    eventTypes: ORDER_EVENT_TYPES,
    onMessage(data) {
      const event = orderEventOf(data);
      if (event === null) {
        return;
      }
      if (event.type === "sales.order.placed") {
        setArrived((current) => new Set(current).add(event.orderId));
      }
      void queryClient.invalidateQueries({ queryKey: getListOrdersQueryKey() });
    },
    onClosed: onStreamClosed,
  });
  const items = orders.data?.pages.flatMap((page) => page.items) ?? [];

  function onSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setQuery(search.trim());
  }

  return (
    <Panel title="Bestellungen" code="VK 01" actions={<ConnectionLamp state={stream.state} onReconnect={stream.reconnect} />}>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <OptionGroup label="Zustand" value={status} onValueChange={(value) => setStatus(value as StatusFilter)}>
          {FILTERS.map((filter) => (
            <OptionPill key={filter.value} value={filter.value} tone="accent">
              {filter.label}
            </OptionPill>
          ))}
        </OptionGroup>
        <form role="search" onSubmit={onSearch} className="flex items-end gap-2">
          <FormField label="Suche" className="w-64">
            {(control) => (
              <Input
                {...control}
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Nummer, E-Mail oder eBay-Nr. …"
              />
            )}
          </FormField>
          <Button type="submit" variant="secondary" size="sm" className="mb-0.5">
            Suchen
          </Button>
        </form>
      </div>

      <div className="mt-6">
        {orders.isPending ? (
          <PendingNotice>Bestellungen werden geladen …</PendingNotice>
        ) : orders.isError ? (
          <p role="alert" className="text-small text-danger">
            {errorMessage(orders.error)}
          </p>
        ) : items.length === 0 ? (
          <p className="rounded-md border border-dashed border-line-strong px-5 py-10 text-center text-small text-ink-secondary">
            {query || status !== "all" ? "Keine Bestellungen für diese Auswahl." : "Noch keine Bestellung eingegangen."}
          </p>
        ) : (
          <>
            <div aria-hidden="true" className={cn(ROW_GRID, "hidden border-b border-line pb-2 label-caps text-ink-tertiary md:grid")}>
              <span>Bestellung</span>
              <span>Empfänger und Artikel</span>
              <span>Zustand</span>
              <span className="text-right">Summe</span>
            </div>
            <ul aria-label="Bestellungen, neueste zuerst" className="divide-y divide-line">
              {items.map((order) => (
                <OrderRow key={order.id} order={order} fresh={arrived.has(order.id)} />
              ))}
            </ul>
          </>
        )}
        {orders.hasNextPage ? (
          <Button
            type="button"
            variant="secondary"
            size="sm"
            className="mt-6"
            disabled={orders.isFetchingNextPage}
            onClick={() => void orders.fetchNextPage()}
          >
            {orders.isFetchingNextPage ? "Lädt …" : "Weitere laden"}
          </Button>
        ) : null}
      </div>
    </Panel>
  );
}

// Phones: number beside the state, recipient below, total last. Wider: one row per order.
const ROW_GRID = "grid grid-cols-[minmax(0,1fr)_auto] gap-x-6 gap-y-1 md:grid-cols-[11rem_minmax(0,1fr)_9rem_6.5rem] md:items-start";

function OrderRow({ order, fresh }: { order: OrderSummaryOut; fresh: boolean }) {
  return (
    <li>
      <Link
        href={`/admin/bestellungen/${order.id}` as Route}
        className={cn(ROW_GRID, "group rounded-sm py-3 text-small hover:bg-stage", fresh && "bg-accent-subtle/50")}
      >
        <span>
          <span className="font-mono font-medium group-hover:underline group-hover:underline-offset-4">{order.number}</span>
          <span className="mt-0.5 flex items-center gap-1.5 text-hint text-ink-tertiary">
            {fresh ? (
              <>
                <SignalLamp color="blue" blinking className="-ml-1" />
                <span className="font-medium text-accent">Neu</span>
                <span aria-hidden="true">·</span>
              </>
            ) : null}
            <time dateTime={order.placed_at}>{formatEventTime(new Date(order.placed_at))}</time>
          </span>
        </span>
        <span className="col-span-2 row-start-2 min-w-0 md:col-span-1 md:row-start-auto">
          <span className="flex items-center gap-2">
            <span className="truncate font-medium">{order.recipient}</span>
            {order.channel === "ebay" ? (
              <ChannelBadge />
            ) : order.guest ? (
              <span className="shrink-0 rounded-full border border-line px-2 text-hint text-ink-tertiary">Gast</span>
            ) : null}
          </span>
          <span className="mt-0.5 block truncate text-hint text-ink-tertiary">
            {order.item_count} Artikel · {order.first_line_title}
          </span>
        </span>
        <StatusBadge tone={ORDER_STATUS_TONES[order.status]} className="col-start-2 row-start-1 justify-self-end md:col-start-auto md:row-start-auto md:justify-self-start">
          {ORDER_STATUS_LABELS[order.status]}
        </StatusBadge>
        <span className="col-start-2 row-start-3 text-right tabular-nums md:col-start-auto md:row-start-auto">
          {formatPrice(order.total_cents)}
        </span>
      </Link>
    </li>
  );
}
