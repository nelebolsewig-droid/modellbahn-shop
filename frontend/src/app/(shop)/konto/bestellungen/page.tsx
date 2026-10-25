import type { Metadata } from "next";

import { AccountNav } from "@/components/account/account-nav";
import { OrderHistory } from "@/components/account/order-history";
import { PageHeading } from "@/components/site/page-heading";

export const metadata: Metadata = {
  title: "Meine Bestellungen",
};

export default function MyOrdersPage() {
  return (
    <div className="mx-auto max-w-6xl px-5 py-14 sm:px-8 lg:py-20">
      <PageHeading caption="Mein Konto" title="Bestellungen" />
      <AccountNav className="mt-10" />
      <OrderHistory />
    </div>
  );
}
