import type { Metadata } from "next";

import { AdminShell } from "@/components/admin/admin-shell";
import { ScalesManager } from "@/components/admin/catalog/scales-manager";

export const metadata: Metadata = { title: "Maßstäbe" };

export default function AdminScalesPage() {
  return (
    <AdminShell>
      <>
        <p className="label-caps text-ink-tertiary">Katalog</p>
        <h1 className="mt-4 mb-8 text-heading sm:text-title">Maßstäbe</h1>
        <ScalesManager />
      </>
    </AdminShell>
  );
}
