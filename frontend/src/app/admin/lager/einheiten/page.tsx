import type { Metadata } from "next";

import { UnitListPage } from "@/components/admin/inventory/inventory-pages";

export const metadata: Metadata = { title: "Stücke" };

function single(value: string | string[] | undefined): string | null {
  return typeof value === "string" && value !== "" ? value : null;
}

/** `?artikel=<variant id>` lists one article's pieces, `?zustand=unverbucht` those never put away. */
export default async function AdminUnitListPage({ searchParams }: PageProps<"/admin/lager/einheiten">) {
  const { artikel, zustand } = await searchParams;
  return <UnitListPage variantId={single(artikel)} filter={single(zustand)} />;
}
