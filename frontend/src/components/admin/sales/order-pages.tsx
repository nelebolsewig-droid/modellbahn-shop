"use client";

import { AdminShell } from "@/components/admin/admin-shell";

import { OrderDesk } from "./order-desk";
import { OrderList } from "./order-list";

// The pages pass functions to the shell, which only client components can do.

export function OrderListPage() {
  return (
    <AdminShell>
      {({ revalidate }) => (
        <>
          <p className="label-caps text-ink-tertiary">Verkauf</p>
          <h1 className="mt-4 mb-8 text-heading sm:text-title">Bestellungen</h1>
          <OrderList onStreamClosed={revalidate} />
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
