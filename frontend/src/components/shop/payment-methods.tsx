"use client";

import { PaymentBadges } from "@/components/shop/payment-badges";
import { useGetPaymentProvider } from "@/lib/api/generated/store-sales/store-sales";
import type { PaymentProvider } from "@/lib/api/generated/model";

const TEXTS: Record<PaymentProvider, string> = {
  sumup:
    "Bezahlen kannst du mit Kredit- oder Debitkarte, PayPal und je nach Gerät auch mit Apple Pay oder Google Pay (über SumUp).",
  mock: "Bezahlt wird hier mit einer Testzahlung; es fließt kein echtes Geld.",
  off: "Im Moment nehmen wir keine Bestellungen an.",
};

/**
 * Which means of payment the shop accepts, said at the start of the ordering process (§ 312j
 * Abs. 1 BGB), together with where it delivers.
 */
export function PaymentMethods({ className }: { className?: string }) {
  const provider = useGetPaymentProvider();
  return (
    <>
      {provider.data?.provider === "sumup" ? <PaymentBadges size="md" className="mt-4" /> : null}
      <p className={className}>
      Wir liefern nach Deutschland und in alle Länder der EU.
      {provider.data ? ` ${TEXTS[provider.data.provider]}` : null}
      {provider.data?.bank_transfer ? " Oder per Vorkasse: Du überweist innerhalb von zehn Tagen, wir verschicken nach Zahlungseingang." : null}
      </p>
    </>
  );
}
