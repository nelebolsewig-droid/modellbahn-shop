import type { Metadata } from "next";

import { LocationPage } from "@/components/admin/inventory/inventory-pages";

export const metadata: Metadata = { title: "Lagerplatz" };

export default async function AdminLocationPage({ params }: PageProps<"/admin/lager/plaetze/[code]">) {
  const { code } = await params;
  return <LocationPage code={decodeURIComponent(code).toUpperCase()} />;
}
