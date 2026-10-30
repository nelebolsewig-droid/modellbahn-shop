import type { Metadata } from "next";

import { PrinterPage } from "@/components/admin/manufacturing/manufacturing-pages";

export const metadata: Metadata = { title: "Drucker" };

export default async function AdminPrinterPage({ params }: PageProps<"/admin/fertigung/drucker/[id]">) {
  const { id } = await params;
  return <PrinterPage printerId={id} />;
}
