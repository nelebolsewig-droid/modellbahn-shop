import type { Metadata } from "next";

import { UnitPage } from "@/components/admin/inventory/inventory-pages";

export const metadata: Metadata = { title: "Stück" };

export default async function AdminUnitPage({ params }: PageProps<"/admin/lager/einheiten/[code]">) {
  const { code } = await params;
  return <UnitPage code={code} />;
}
