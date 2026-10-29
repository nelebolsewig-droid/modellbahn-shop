import type { Metadata } from "next";

import { AdminShell } from "@/components/admin/admin-shell";
import { QuickEntryDesk } from "@/components/admin/catalog/quick-entry";

export const metadata: Metadata = { title: "Schnellerfassung" };

/** One model off the shelf in one go, made for the phone at the crates. */
export default function AdminQuickEntryPage() {
  return (
    <AdminShell>
      <QuickEntryDesk />
    </AdminShell>
  );
}
