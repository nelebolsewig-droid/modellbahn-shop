import type { Metadata } from "next";

import { AdminShell } from "@/components/admin/admin-shell";
import { ProductList } from "@/components/admin/catalog/product-list";

export const metadata: Metadata = { title: "Katalog" };

export default function AdminCatalogPage() {
  return (
    <AdminShell>
      <>
        <p className="label-caps text-ink-tertiary">Katalog</p>
        <h1 className="mt-4 mb-8 text-heading sm:text-title">Produkte</h1>
        <ProductList />
      </>
    </AdminShell>
  );
}
