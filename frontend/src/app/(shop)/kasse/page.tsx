import type { Metadata } from "next";

import { CheckoutView } from "@/components/shop/checkout-view";
import { PageHeading } from "@/components/site/page-heading";

export const metadata: Metadata = {
  title: "Kasse",
  robots: { index: false, follow: false },
};

export default function CheckoutPage() {
  return (
    <div className="mx-auto max-w-6xl px-5 py-12 sm:px-8 lg:py-20">
      <PageHeading caption="Bestellung" title="Kasse" />
      <CheckoutView />
    </div>
  );
}
