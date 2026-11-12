import type { Metadata } from "next";

import { AdminShell } from "@/components/admin/admin-shell";
import { ScalesManager } from "@/components/admin/catalog/scales-manager";
import { SettingsBackLink } from "@/components/admin/settings/settings-page";

export const metadata: Metadata = { title: "Maßstäbe" };

export default function AdminScalesPage() {
  return (
    <AdminShell>
      <>
        <SettingsBackLink />
        <h1 className="mt-6 mb-8 text-heading sm:text-title">Maßstäbe</h1>
        <ScalesManager />
      </>
    </AdminShell>
  );
}
