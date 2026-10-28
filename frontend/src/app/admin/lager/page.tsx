import type { Metadata } from "next";

import { InventoryPage } from "@/components/admin/inventory/inventory-pages";

export const metadata: Metadata = { title: "Lager" };

export default function AdminInventoryPage() {
  return <InventoryPage />;
}
