import type { Metadata } from "next";

import { PageHeading } from "@/components/site/page-heading";

export const metadata: Metadata = {
  title: "Allgemeine Geschäftsbedingungen",
};

export default function TermsPage() {
  return (
    <div className="mx-auto max-w-6xl px-5 py-12 sm:px-8 lg:py-20">
      <PageHeading caption="Rechtliches" title="Allgemeine Geschäftsbedingungen">
        <p>
          Die Geschäftsbedingungen des Shops stehen hier, sobald der Inhaber sie festgelegt hat. Vor
          dem Verkaufsstart ist diese Seite vollständig; bis dahin sind Bestellungen Testbestellungen
          ohne echte Zahlung.
        </p>
      </PageHeading>
    </div>
  );
}
