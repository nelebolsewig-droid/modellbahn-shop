import type { Metadata } from "next";

import { NewsletterLink } from "@/components/account/newsletter-link";
import { FormPage } from "@/components/site/form-page";
import { firstParam } from "@/lib/search-params";

export const metadata: Metadata = {
  title: "Newsletter bestätigen",
  referrer: "no-referrer",
  robots: { index: false },
};

export default async function ConfirmNewsletterPage({ searchParams }: PageProps<"/newsletter/bestaetigen">) {
  const token = firstParam((await searchParams).token) || null;
  return (
    <FormPage caption="Newsletter" title="Bestätigen">
      <NewsletterLink action="confirm" token={token} />
    </FormPage>
  );
}
