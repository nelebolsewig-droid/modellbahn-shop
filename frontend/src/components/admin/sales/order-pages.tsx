"use client";

import { useState } from "react";

import { AdminShell } from "@/components/admin/admin-shell";
import { OptionGroup, OptionPill } from "@/components/ui/option-pill";
import type { OrderStatus } from "@/lib/api/generated/model";

import { OrderDesk } from "./order-desk";
import { OrderList } from "./order-list";
import { OrderTrack } from "./order-track";
import { RepaymentsPanel } from "./repayment-panel";
import { WithdrawalsPanel } from "./withdrawals";

// The pages pass functions to the shell, which only client components can do.

type OrderView = { mode: "track" } | { mode: "list"; status: OrderStatus };

/**
 * Bestellungen: the Gleisbild shows where every open order stands; the list beside it
 * filters, searches and reaches back to the oldest order.
 */
export function OrderListPage() {
  const [view, setView] = useState<OrderView>({ mode: "track" });
  return (
    <AdminShell>
      {({ staff, revalidate }) => (
        <>
          <div className="mb-8 flex flex-wrap items-end justify-between gap-x-8 gap-y-5">
            <div>
              <p className="label-caps text-ink-secondary">
                {view.mode === "track" ? "Übersicht · von der Bestellung bis zum Paket" : "Verkauf · Liste"}
              </p>
              <h1 className="mt-3 text-title sm:text-display">{view.mode === "track" ? "Wo steht was?" : "Bestellungen"}</h1>
            </div>
            <OptionGroup
              label="Ansicht"
              value={view.mode}
              onValueChange={(mode) => setView(mode === "list" ? { mode: "list", status: "paid" } : { mode: "track" })}
            >
              <OptionPill value="track">Übersicht</OptionPill>
              <OptionPill value="list">Liste</OptionPill>
            </OptionGroup>
          </div>
          {staff.role === "owner" || staff.role === "staff" ? <RepaymentsPanel /> : null}
          <WithdrawalsPanel />
          {view.mode === "track" ? (
            <OrderTrack
              staffRole={staff.role}
              onStreamClosed={revalidate}
              onOpenList={(status) => setView({ mode: "list", status })}
            />
          ) : (
            <OrderList staffRole={staff.role} onStreamClosed={revalidate} initialStatus={view.status} />
          )}
        </>
      )}
    </AdminShell>
  );
}

export function OrderDeskPage({ orderId }: { orderId: string }) {
  return (
    <AdminShell>
      {({ staff, revalidate }) => <OrderDesk orderId={orderId} staffRole={staff.role} onStreamClosed={revalidate} />}
    </AdminShell>
  );
}
