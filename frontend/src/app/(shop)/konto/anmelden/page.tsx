import type { Metadata } from "next";

import { CustomerLogin } from "@/components/account/customer-login";
import { FormPage } from "@/components/site/form-page";
import { TextLink } from "@/components/ui/text-link";
import { CUSTOMER_AREA, RETURN_TO_PARAM, safeReturnPath } from "@/lib/navigation";
import { firstParam } from "@/lib/search-params";

export const metadata: Metadata = {
  title: "Anmelden",
};

export default async function LoginPage({ searchParams }: PageProps<"/konto/anmelden">) {
  const returnTo = safeReturnPath(firstParam((await searchParams)[RETURN_TO_PARAM]), CUSTOMER_AREA);
  return (
    <FormPage
      caption="Kundenkonto"
      title="Anmelden"
      intro={<p>Melde dich mit deiner E-Mail-Adresse und deinem Passwort an.</p>}
      footer={
        <>
          <p>
            <TextLink href="/konto/passwort-vergessen">Passwort vergessen?</TextLink>
          </p>
          <p>
            Noch kein Konto? <TextLink href="/konto/registrieren">Jetzt registrieren</TextLink>
          </p>
        </>
      }
    >
      <CustomerLogin returnTo={returnTo} />
    </FormPage>
  );
}
