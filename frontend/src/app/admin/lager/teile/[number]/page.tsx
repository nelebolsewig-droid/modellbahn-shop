import type { Metadata } from "next";

import { PartPage } from "@/components/admin/inventory/inventory-pages";

export const metadata: Metadata = { title: "Teil im Lager" };

export default async function AdminPartStockPage({ params }: PageProps<"/admin/lager/teile/[number]">) {
  const { number } = await params;
  return <PartPage partNumber={decodeURIComponent(number).toUpperCase()} />;
}
