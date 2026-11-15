import type { Metadata } from "next";

import { AdminShell } from "@/components/admin/admin-shell";
import { CategoriesManager } from "@/components/admin/catalog/categories-manager";
import { SettingsBackLink } from "@/components/admin/settings/settings-page";

export const metadata: Metadata = { title: "Kategorien" };

export default function AdminCategoriesPage() {
  return (
    <AdminShell>
      <>
        <SettingsBackLink />
        <h1 className="mt-6 mb-8 text-heading sm:text-title">Kategorien</h1>
        <CategoriesManager />
      </>
    </AdminShell>
  );
}
