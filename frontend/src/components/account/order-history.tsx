"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import type { Route } from "next";
import Link from "next/link";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { PendingNotice } from "@/components/ui/pending-notice";
import { StatusBadge } from "@/components/ui/status-badge";
import type { OrderPageOut, OrderSummaryOut } from "@/lib/api/generated/model";
import { getListMyOrdersQueryKey, listMyOrders } from "@/lib/api/generated/store-account/store-account";
import type { ApiProblem } from "@/lib/api/problem";
import { formatPrice } from "@/lib/catalog/format";
import { formatLongDate } from "@/lib/format";
import { errorMessage } from "@/lib/i18n/problems";
import { ORDER_STATUS_LABELS, ORDER_STATUS_TONES } from "@/lib/sales/labels";

import { CustomerGate } from "./customer-gate";

const PAGE_SIZE = 20;

/** "Meine Bestellungen": every order of the account, newest first, adopted guest orders included. */
export function OrderHistory() {
  return <CustomerGate pending="Deine Bestellungen werden geladen …">{() => <OrderList />}</CustomerGate>;
}

function OrderList() {
  const orders = useInfiniteQuery<OrderPageOut, ApiProblem>({
    queryKey: [...getListMyOrdersQueryKey(), "pages"],
    queryFn: ({ pageParam, signal }) =>
      listMyOrders(
        { limit: PAGE_SIZE, ...(typeof pageParam === "string" && { cursor: pageParam }) },
        { signal },
      ),
    initialPageParam: null,
    getNextPageParam: (page) => page.next_cursor,
  });

  if (orders.isPending) {
    return <PendingNotice className="mt-10">Deine Bestellungen werden geladen …</PendingNotice>;
  }
  if (orders.isError) {
    return (
      <Alert tone="danger" title="Deine Bestellungen konnten nicht geladen werden" className="mt-10 max-w-xl">
        <p>{errorMessage(orders.error)}</p>
      </Alert>
    );
  }
  const items = orders.data.pages.flatMap((page) => page.items);

  return (
    <div className="mt-10">
      {items.length === 0 ? (
        <div className="rounded-lg border border-dashed border-line-strong px-6 py-14 text-center">
          <p className="text-heading">Noch keine Bestellungen</p>
          <p className="mx-auto mt-3 max-w-md text-ink-secondary">
            Sobald du etwas bestellst, findest du es hier – mit Status, Sendungsnummer und Rechnungsbetrag.
          </p>
          <Button asChild className="mt-8">
            <Link href="/katalog">Zum Katalog</Link>
          </Button>
        </div>
      ) : (
        <ol aria-label="Bestellungen" className="divide-y divide-line border-y border-line">
          {items.map((order) => (
            <OrderRow key={order.id} order={order} />
          ))}
        </ol>
      )}
      {orders.hasNextPage ? (
        <Button
          type="button"
          variant="secondary"
          className="mt-8"
          disabled={orders.isFetchingNextPage}
          aria-busy={orders.isFetchingNextPage || undefined}
          onClick={() => void orders.fetchNextPage()}
        >
          {orders.isFetchingNextPage ? "Lädt …" : "Ältere Bestellungen laden"}
        </Button>
      ) : null}
      <p className="mt-8 max-w-xl text-hint text-ink-tertiary">
        Als Gast bestellt? Bestellungen mit derselben, bestätigten E-Mail-Adresse erscheinen hier von selbst.
      </p>
    </div>
  );
}

function OrderRow({ order }: { order: OrderSummaryOut }) {
  return (
    <li>
      {/* Phones: number and date beside status and total, the article below.
          Wider: one timetable row, the columns in reading order. */}
      <Link
        href={`/konto/bestellungen/${order.number}` as Route}
        className="group grid grid-cols-[minmax(0,1fr)_auto] items-start gap-x-6 gap-y-3 py-5 sm:grid-cols-[9.5rem_minmax(0,1fr)_8rem_7rem_1rem] sm:items-center"
      >
        <span className="font-mono text-small sm:order-1">
          {order.number}
          <span className="mt-0.5 block font-sans text-hint text-ink-tertiary">
            <time dateTime={order.placed_at}>{formatLongDate(new Date(order.placed_at))}</time>
          </span>
        </span>
        <span className="flex flex-col items-end gap-1 sm:contents">
          <StatusBadge tone={ORDER_STATUS_TONES[order.status]} className="sm:order-3">
            {ORDER_STATUS_LABELS[order.status]}
          </StatusBadge>
          <span className="tabular-nums sm:order-4 sm:text-right">{formatPrice(order.total_cents)}</span>
        </span>
        <span className="col-span-2 min-w-0 sm:order-2 sm:col-span-1">
          <span className="block truncate font-medium group-hover:underline group-hover:underline-offset-4">
            {order.first_line_title}
          </span>
          <span className="mt-0.5 block text-hint text-ink-tertiary">
            {order.item_count} Artikel · an {order.recipient}
          </span>
        </span>
        <span aria-hidden="true" className="hidden text-ink-tertiary transition-transform group-hover:translate-x-0.5 sm:order-5 sm:block">
          →
        </span>
      </Link>
    </li>
  );
}
