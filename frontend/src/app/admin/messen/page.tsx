import type { Metadata } from "next";

import { AdminShell } from "@/components/admin/admin-shell";
import { FairsManager } from "@/components/admin/site/fairs-manager";

export const metadata: Metadata = { title: "Messen" };

export default function AdminFairsPage() {
  return (
    <AdminShell>
      <>
        <p className="label-caps text-ink-tertiary">Auftritt</p>
        <h1 className="mt-4 mb-8 text-heading sm:text-title">Messen</h1>
        <FairsManager />
      </>
    </AdminShell>
  );
}
