import type { Metadata } from "next";
import Link from "next/link";

import { AdminShell } from "@/components/admin/admin-shell";
import { ProductList } from "@/components/admin/catalog/product-list";
import { Button } from "@/components/ui/button";
import { getExportArticlesUrl } from "@/lib/api/generated/admin-catalog/admin-catalog";

export const metadata: Metadata = { title: "Modelle" };

export default function AdminModelsPage() {
  return (
    <AdminShell>
      <>
        <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <h1 className="text-heading sm:text-title">Modelle</h1>
          <div className="flex flex-wrap items-center gap-2">
            <Button asChild size="sm" variant="ghost">
              {/* Every variant with EAN and price, to import into the till (SumUp). */}
              <a href={getExportArticlesUrl()} download>
                Liste für die Kasse (CSV)
              </a>
            </Button>
            <Button asChild>
              <Link href="/admin/modelle/neu">Neues Modell</Link>
            </Button>
          </div>
        </div>
        <ProductList />
      </>
    </AdminShell>
  );
}
