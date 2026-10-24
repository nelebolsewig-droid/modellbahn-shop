import type { Metadata } from "next";

import { AdminShell } from "@/components/admin/admin-shell";
import { CategoriesManager } from "@/components/admin/catalog/categories-manager";

export const metadata: Metadata = { title: "Kategorien" };

export default function AdminCategoriesPage() {
  return (
    <AdminShell>
      <>
        <p className="label-caps text-ink-tertiary">Katalog</p>
        <h1 className="mt-4 mb-8 text-heading sm:text-title">Kategorien</h1>
        <CategoriesManager />
      </>
    </AdminShell>
  );
}
