import type { Metadata } from "next";

import { FairNewsLink } from "@/components/site/fair-news-link";
import { FormPage } from "@/components/site/form-page";
import { firstParam } from "@/lib/search-params";

export const metadata: Metadata = {
  title: "Messe-Post abbestellen",
  referrer: "no-referrer",
  robots: { index: false },
};

export default async function UnsubscribeFairNewsPage({ searchParams }: PageProps<"/termine/abmelden">) {
  const token = firstParam((await searchParams).token) || null;
  return (
    <FormPage caption="Messe-Post" title="Abmelden">
      <FairNewsLink action="unsubscribe" token={token} />
    </FormPage>
  );
}
