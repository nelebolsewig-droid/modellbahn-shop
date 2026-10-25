import type { Metadata } from "next";

import { OrderStatusView } from "@/components/shop/order-status";

export const metadata: Metadata = {
  title: "Deine Bestellung",
  // The address is a secret of the customer; it must never end up in a search index.
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

export default async function OrderStatusPage({ params }: PageProps<"/bestellung/[token]">) {
  const { token } = await params;
  return (
    <div className="mx-auto max-w-6xl px-5 py-12 sm:px-8 lg:py-20">
      <OrderStatusView token={token} />
    </div>
  );
}
