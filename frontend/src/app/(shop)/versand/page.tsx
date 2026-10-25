import type { Metadata } from "next";

import { ShippingRates } from "@/components/shop/shipping-rates";
import { PageHeading } from "@/components/site/page-heading";

export const metadata: Metadata = {
  title: "Versand und Lieferung",
};

export default function ShippingPage() {
  return (
    <div className="mx-auto max-w-6xl px-5 py-12 sm:px-8 lg:py-20">
      <PageHeading caption="Service" title="Versand und Lieferung">
        <p>
          Wir liefern nach Deutschland und Österreich. Alle Preise enthalten 19 % Mehrwertsteuer; die
          Versandkosten kommen einmal pro Bestellung dazu und entfallen ab dem genannten Warenwert.
        </p>
      </PageHeading>
      <div className="mt-10">
        <ShippingRates />
      </div>
      <p className="mt-8 max-w-xl text-small text-ink-secondary">
        Viele Modelle drucken wir erst nach der Bestellung. Wie lange das dauert, zeigt der Shop
        künftig an jedem Artikel an.
      </p>
    </div>
  );
}
