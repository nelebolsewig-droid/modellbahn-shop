import type { Metadata } from "next";

import { VerifyEmail } from "@/components/account/verify-email";
import { FormPage } from "@/components/site/form-page";
import { firstParam } from "@/lib/search-params";

export const metadata: Metadata = {
  title: "E-Mail-Adresse bestätigen",
  // The one-time token is in the address; it must not travel on in a Referer header.
  referrer: "no-referrer",
};

export default async function VerifyEmailPage({ searchParams }: PageProps<"/konto/bestaetigen">) {
  const token = firstParam((await searchParams).token) || null;
  return (
    <FormPage caption="Kundenkonto" title="E-Mail bestätigen">
      <VerifyEmail token={token} />
    </FormPage>
  );
}
