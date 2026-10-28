import type { Metadata } from "next";

import { FairNewsLink } from "@/components/site/fair-news-link";
import { FormPage } from "@/components/site/form-page";
import { firstParam } from "@/lib/search-params";

export const metadata: Metadata = {
  title: "Messe-Post bestätigen",
  // The one-time token is in the address; it must not travel on in a Referer header.
  referrer: "no-referrer",
  robots: { index: false },
};

export default async function ConfirmFairNewsPage({ searchParams }: PageProps<"/termine/bestaetigen">) {
  const token = firstParam((await searchParams).token) || null;
  return (
    <FormPage caption="Messe-Post" title="Anmeldung bestätigen">
      <FairNewsLink action="confirm" token={token} />
    </FormPage>
  );
}
