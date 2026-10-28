"use client";

import { AdminShell } from "@/components/admin/admin-shell";

import { InventoryOverview } from "./inventory-overview";
import { ScannerDesk } from "./scanner-desk";

// The pages pass functions to the shell, which only client components can do.

export function ScannerPage({ orderId }: { orderId: string | null }) {
  return (
    <AdminShell>
      {({ staff, revalidate }) => <ScannerDesk staffRole={staff.role} initialOrderId={orderId} onStreamClosed={revalidate} />}
    </AdminShell>
  );
}

export function InventoryPage() {
  return (
    <AdminShell>
      {({ staff, revalidate }) => <InventoryOverview staffRole={staff.role} onStreamClosed={revalidate} />}
    </AdminShell>
  );
}
