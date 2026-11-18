"use client";

import { useQuery } from "@tanstack/react-query";

import { getListOrdersQueryKey, listOrders } from "@/lib/api/generated/admin-sales/admin-sales";
import { useListToMake } from "@/lib/api/generated/admin-inventory/admin-inventory";
import type { OrderPageOut, OrderStatus, OrderSummaryOut } from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";

/** As many orders as one request brings; a lane with more says so ("50+"). */
export const LANE_LIMIT = 50;

/**
 * The newest orders in one state, for the tiles of Heute and the stations of the
 * Gleisbild. Lives under the order list's key, so every order event renews it too.
 */
export function useOrderLane(status: OrderStatus, limit = LANE_LIMIT) {
  return useQuery<OrderPageOut, ApiProblem>({
    queryKey: [...getListOrdersQueryKey(), "lane", status, limit],
    queryFn: ({ signal }) => listOrders({ status: [status], limit }, { signal }),
    refetchInterval: 60_000,
  });
}

/** "7", or "50+" when the lane holds more than one request brought. */
export function laneCount(page: OrderPageOut | undefined, shown?: number): string {
  if (page === undefined) {
    return "–";
  }
  return `${shown ?? page.items.length}${page.next_cursor ? "+" : ""}`;
}

/**
 * The ids of paid orders that still wait for a piece from the workshop (ADR 0029).
 * Only owner and staff may ask; for a packer the set stays empty.
 */
export function useWaitingOrderIds(enabled: boolean): ReadonlySet<string> {
  const toMake = useListToMake({
    query: {
      enabled,
      refetchInterval: 60_000,
      select: (data) => data.items.flatMap((row) => row.orders.map((order) => order.order_id)),
    },
  });
  return new Set(enabled ? (toMake.data ?? []) : []);
}

/** Paid orders in two piles: complete and ready to pack, or waiting for the workshop. */
export function splitPaid(paid: readonly OrderSummaryOut[], waiting: ReadonlySet<string>) {
  return {
    ready: paid.filter((order) => !waiting.has(order.id)),
    making: paid.filter((order) => waiting.has(order.id)),
  };
}

/** How long an order has been around: "heute", "1 T", "4 T" (whole days). */
export function orderAge(placedAt: string, now: Date): { short: string; long: string } {
  const days = Math.max(0, Math.floor((now.getTime() - new Date(placedAt).getTime()) / 86_400_000));
  if (days === 0) {
    return { short: "heute", long: "seit heute" };
  }
  return { short: `${days} T`, long: days === 1 ? "seit einem Tag" : `seit ${days} Tagen` };
}
