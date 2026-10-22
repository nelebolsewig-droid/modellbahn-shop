import type { Metadata } from "next";

import { RegistrationForm } from "@/components/account/registration-form";
import { FormPage } from "@/components/site/form-page";
import { TextLink } from "@/components/ui/text-link";

export const metadata: Metadata = {
  title: "Registrieren",
};

export default function RegistrationPage() {
  return (
    <FormPage
      caption="Kundenkonto"
      title="Registrieren"
      intro={
        <>
          <p>
            Mit einem Kundenkonto behältst du später deine Bestellungen im Blick. Nach dem Absenden
            schicken wir dir eine E-Mail; mit dem Link darin bestätigst du deine Adresse.
          </p>
          <p>
            Was wir speichern, steht unter <TextLink href="/datenschutz">Datenschutz</TextLink>.
          </p>
        </>
      }
      footer={
        <p>
          Schon registriert? <TextLink href="/konto/anmelden">Anmelden</TextLink>
        </p>
      }
    >
      <RegistrationForm />
    </FormPage>
  );
}
