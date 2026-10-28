"use client";

import { AdminShell } from "@/components/admin/admin-shell";

import { InventoryOverview } from "./inventory-overview";
import { LocationDesk } from "./location-desk";
import { ScannerDesk } from "./scanner-desk";
import { UnitDesk } from "./unit-desk";

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

export function LocationPage({ code }: { code: string }) {
  return (
    <AdminShell>
      {({ staff, revalidate }) => <LocationDesk code={code} staffRole={staff.role} onStreamClosed={revalidate} />}
    </AdminShell>
  );
}

export function UnitPage({ code }: { code: string }) {
  return (
    <AdminShell>
      {({ staff, revalidate }) => <UnitDesk code={code} staffRole={staff.role} onStreamClosed={revalidate} />}
    </AdminShell>
  );
}
