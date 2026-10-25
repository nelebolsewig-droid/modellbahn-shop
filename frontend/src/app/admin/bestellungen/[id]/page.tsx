import type { Metadata } from "next";

import { OrderDeskPage } from "@/components/admin/sales/order-pages";

export const metadata: Metadata = { title: "Bestellung" };

export default async function AdminOrderPage({ params }: PageProps<"/admin/bestellungen/[id]">) {
  const { id } = await params;
  return <OrderDeskPage orderId={id} />;
}
