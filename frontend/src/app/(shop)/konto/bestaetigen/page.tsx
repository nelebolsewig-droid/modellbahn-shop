import type { Metadata } from "next";

import { VerifyEmail } from "@/components/account/verify-email";
import { FormPage } from "@/components/site/form-page";
import { TextLink } from "@/components/ui/text-link";
import { firstParam } from "@/lib/search-params";

export const metadata: Metadata = {
  title: "E-Mail-Adresse bestätigen",
  // The one-time token is in the address; it must not travel on in a Referer header.
  referrer: "no-referrer",
};

export default async function VerifyEmailPage({ searchParams }: PageProps<"/konto/bestaetigen">) {
  const token = firstParam((await searchParams).token) || null;
  return (
    <FormPage
      caption="Kundenkonto"
      title="E-Mail bestätigen"
      intro={
        <p>
          Gib zur Sicherheit das Passwort ein, das du bei der Registrierung gewählt hast. Der Link
          allein genügt so niemandem, um ein Konto zu übernehmen. Danach bist du gleich angemeldet.
        </p>
      }
      footer={
        <p>
          Passwort vergessen?{" "}
          <TextLink href="/konto/passwort-vergessen">Neues Passwort festlegen</TextLink> – der
          Link dafür bestätigt deine Adresse ebenfalls.
        </p>
      }
    >
      <VerifyEmail token={token} />
    </FormPage>
  );
}
