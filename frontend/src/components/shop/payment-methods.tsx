"use client";

import { useGetPaymentProvider } from "@/lib/api/generated/store-sales/store-sales";
import type { PaymentProvider } from "@/lib/api/generated/model";

const TEXTS: Record<PaymentProvider, string> = {
  sumup:
    "Bezahlen kannst du mit Kredit- oder Debitkarte, je nach Gerät auch mit Apple Pay oder Google Pay (über SumUp).",
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
    <p className={className}>
      Wir liefern nach Deutschland und in alle Länder der EU.
      {provider.data ? ` ${TEXTS[provider.data.provider]}` : null}
    </p>
  );
}
