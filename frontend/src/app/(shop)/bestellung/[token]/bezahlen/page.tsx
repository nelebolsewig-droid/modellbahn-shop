import type { Metadata } from "next";

import { PaymentView } from "@/components/shop/payment-view";

export const metadata: Metadata = {
  title: "Bezahlen",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

export default async function PaymentPage({ params }: PageProps<"/bestellung/[token]/bezahlen">) {
  const { token } = await params;
  return (
    <div className="mx-auto max-w-3xl px-5 py-12 sm:px-8 lg:py-20">
      <PaymentView token={token} />
    </div>
  );
}
