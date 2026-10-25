import type { Metadata } from "next";

import { OrderListPage } from "@/components/admin/sales/order-pages";

export const metadata: Metadata = { title: "Bestellungen" };

export default function AdminOrdersPage() {
  return <OrderListPage />;
}
