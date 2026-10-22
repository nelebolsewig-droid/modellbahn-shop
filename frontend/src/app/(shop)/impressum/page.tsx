import type { Metadata } from "next";

import { PageHeading } from "@/components/site/page-heading";

export const metadata: Metadata = {
  title: "Impressum",
};

export default function ImprintPage() {
  return (
    <div className="mx-auto max-w-6xl px-5 py-12 sm:px-8 lg:py-20">
      <PageHeading caption="Rechtliches" title="Impressum">
        <p>
          Die Anbieterangaben nach § 5 DDG – Name, Anschrift und Kontakt – stehen hier, sobald
          Name und Sitz des Shops feststehen. Vor dem Verkaufsstart ist diese Seite vollständig.
        </p>
      </PageHeading>
    </div>
  );
}
