import type { Metadata } from "next";

import { ResendVerification } from "@/components/account/resend-verification";
import { FormPage } from "@/components/site/form-page";
import { TextLink } from "@/components/ui/text-link";

export const metadata: Metadata = {
  title: "Bestätigungslink anfordern",
};

export default function ResendVerificationPage() {
  return (
    <FormPage
      caption="Kundenkonto"
      title="Neuer Bestätigungslink"
      intro={
        <p>
          Der Link aus der E-Mail ist abgelaufen oder nicht angekommen? Gib deine E-Mail-Adresse
          ein, dann schicken wir dir einen neuen.
        </p>
      }
      footer={
        <p>
          Schon bestätigt? <TextLink href="/konto/anmelden">Anmelden</TextLink>
        </p>
      }
    >
      <ResendVerification />
    </FormPage>
  );
}
