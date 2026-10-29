import type { Metadata } from "next";

import { HallPage } from "@/components/admin/manufacturing/manufacturing-pages";

export const metadata: Metadata = { title: "Fertigung" };

export default function AdminManufacturingPage() {
  return <HallPage />;
}
