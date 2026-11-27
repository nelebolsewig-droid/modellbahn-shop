import type { Metadata } from "next";

import { NewsletterLink } from "@/components/account/newsletter-link";
import { FormPage } from "@/components/site/form-page";
import { firstParam } from "@/lib/search-params";

export const metadata: Metadata = {
  title: "Newsletter abbestellen",
  referrer: "no-referrer",
  robots: { index: false },
};

export default async function UnsubscribeNewsletterPage({ searchParams }: PageProps<"/newsletter/abmelden">) {
  const token = firstParam((await searchParams).token) || null;
  return (
    <FormPage caption="Newsletter" title="Abbestellen">
      <NewsletterLink action="unsubscribe" token={token} />
    </FormPage>
  );
}
