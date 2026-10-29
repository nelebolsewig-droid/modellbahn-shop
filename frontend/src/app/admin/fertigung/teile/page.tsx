import type { Metadata } from "next";

import { PartsPage } from "@/components/admin/manufacturing/manufacturing-pages";

export const metadata: Metadata = { title: "Teile und Material" };

export default function AdminPartsPage() {
  return <PartsPage />;
}
