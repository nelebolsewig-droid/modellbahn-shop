import type { Metadata } from "next";

import { PageHeading } from "@/components/site/page-heading";

export const metadata: Metadata = {
  title: "Widerrufsbelehrung",
};

export default function WithdrawalPage() {
  return (
    <div className="mx-auto max-w-6xl px-5 py-12 sm:px-8 lg:py-20">
      <PageHeading caption="Rechtliches" title="Widerrufsbelehrung">
        <p>
          Die Widerrufsbelehrung mit dem Muster-Widerrufsformular steht hier, sobald Name und
          Anschrift des Shops feststehen. Vor dem Verkaufsstart ist diese Seite vollständig.
        </p>
      </PageHeading>
    </div>
  );
}
