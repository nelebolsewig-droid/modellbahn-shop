import type { Metadata } from "next";

import { ShippingRates } from "@/components/shop/shipping-rates";
import { PageHeading } from "@/components/site/page-heading";

export const metadata: Metadata = {
  title: "Versand und Lieferung",
};

const TIMES = [
  {
    term: "Vorrätige Modelle",
    details: "Wir verschicken sie in der Regel 1–3 Werktage, nachdem deine Zahlung eingegangen ist.",
  },
  {
    term: "Auf Bestellung gefertigt",
    details:
      "Manche Modelle bauen wir erst für dich. Die Lieferzeit steht am Artikel und vor dem Kauf im Warenkorb; bei aufwendigen Modellen sind es bis zu drei Monate.",
  },
  {
    term: "Unterwegs",
    details: "Innerhalb Deutschlands ist dein Paket meist 2–5 Werktage unterwegs, in die übrigen EU-Länder etwas länger.",
  },
] as const;

export default function ShippingPage() {
  return (
    <div className="mx-auto max-w-6xl px-5 py-12 sm:px-8 lg:py-20">
      <PageHeading caption="Service" title="Versand und Lieferung">
        <p>
          Wir liefern innerhalb Deutschlands und in alle Länder der Europäischen Union. Die Versandkosten kommen
          einmal pro Bestellung dazu; alle Preise enthalten die gesetzliche Mehrwertsteuer.
        </p>
      </PageHeading>
      <div className="mt-10">
        <ShippingRates />
      </div>
      <section aria-labelledby="lieferzeit" className="mt-16 max-w-3xl">
        <h2 id="lieferzeit" className="text-heading">
          Wann dein Paket kommt
        </h2>
        <dl className="mt-6 divide-y divide-line border-y border-line">
          {TIMES.map((time) => (
            <div key={time.term} className="grid gap-2 py-5 sm:grid-cols-[14rem_minmax(0,1fr)] sm:gap-8">
              <dt className="font-medium">{time.term}</dt>
              <dd className="text-ink-secondary">{time.details}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}
