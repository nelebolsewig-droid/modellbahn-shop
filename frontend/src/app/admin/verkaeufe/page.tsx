import type { Metadata } from "next";

import { AdminShell } from "@/components/admin/admin-shell";
import { SalesDesk } from "@/components/admin/sales/sales-desk";

export const metadata: Metadata = { title: "Verkäufe" };

export default function AdminSalesPage() {
  return (
    <AdminShell>
      <>
        <p className="label-caps text-ink-tertiary">Umsatz</p>
        <h1 className="mt-4 mb-8 text-heading sm:text-title">Verkäufe</h1>
        <SalesDesk />
      </>
    </AdminShell>
  );
}
