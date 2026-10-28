import type { Metadata } from "next";

import { ScannerPage } from "@/components/admin/inventory/inventory-pages";

export const metadata: Metadata = { title: "Scanner" };

/** `?bestellung=<id>` opens the scanner ready to pick that order (link on the order desk). */
export default async function AdminScannerPage({ searchParams }: PageProps<"/admin/scanner">) {
  const { bestellung } = await searchParams;
  return <ScannerPage orderId={typeof bestellung === "string" && bestellung !== "" ? bestellung : null} />;
}
