import type { Metadata } from "next";

import { AssemblyPage } from "@/components/admin/inventory/inventory-pages";

export const metadata: Metadata = { title: "Montage" };

export default function AdminAssemblyPage() {
  return <AssemblyPage />;
}
