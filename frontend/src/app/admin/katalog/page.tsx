import type { Metadata } from "next";

import { AdminShell } from "@/components/admin/admin-shell";
import { ProductList } from "@/components/admin/catalog/product-list";
import { Button } from "@/components/ui/button";
import { getExportArticlesUrl } from "@/lib/api/generated/admin-catalog/admin-catalog";

export const metadata: Metadata = { title: "Katalog" };

export default function AdminCatalogPage() {
  return (
    <AdminShell>
      <>
        <p className="label-caps text-ink-tertiary">Katalog</p>
        <div className="mt-4 mb-8 flex flex-wrap items-end justify-between gap-4">
          <h1 className="text-heading sm:text-title">Produkte</h1>
          <Button asChild size="sm" variant="ghost">
            {/* Every variant with EAN and price, to import into the till (SumUp). */}
            <a href={getExportArticlesUrl()} download>
              Artikelliste für die Kasse (CSV)
            </a>
          </Button>
        </div>
        <ProductList />
      </>
    </AdminShell>
  );
}
