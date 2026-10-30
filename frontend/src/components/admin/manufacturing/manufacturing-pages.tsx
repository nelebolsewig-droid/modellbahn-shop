"use client";

import { AdminShell } from "@/components/admin/admin-shell";

import { PartsDesk } from "./parts-desk";
import { PrinterDesk } from "./printer-desk";
import { PrinterHall } from "./printer-hall";

// The pages pass functions to the shell, which only client components can do.

export function HallPage() {
  return (
    <AdminShell>
      {({ staff, revalidate }) => <PrinterHall staffRole={staff.role} onStreamClosed={revalidate} />}
    </AdminShell>
  );
}

export function PartsPage() {
  return <AdminShell>{({ staff }) => <PartsDesk staffRole={staff.role} />}</AdminShell>;
}

export function PrinterPage({ printerId }: { printerId: string }) {
  return (
    <AdminShell>
      {({ staff, revalidate }) => (
        <PrinterDesk printerId={printerId} staffRole={staff.role} onStreamClosed={revalidate} />
      )}
    </AdminShell>
  );
}
