import type { Metadata } from "next";

import { CartView } from "@/components/shop/cart-view";
import { PageHeading } from "@/components/site/page-heading";

export const metadata: Metadata = {
  title: "Warenkorb",
  robots: { index: false, follow: true },
};

export default function CartPage() {
  return (
    <div className="mx-auto max-w-6xl px-5 py-12 sm:px-8 lg:py-20">
      <PageHeading caption="Bestellung" title="Warenkorb" />
      <CartView />
    </div>
  );
}
