import type { Metadata } from "next";

import { PasswordForgotten } from "@/components/account/password-forgotten";
import { FormPage } from "@/components/site/form-page";
import { TextLink } from "@/components/ui/text-link";

export const metadata: Metadata = {
  title: "Passwort vergessen",
};

export default function PasswordForgottenPage() {
  return (
    <FormPage
      caption="Kundenkonto"
      title="Passwort vergessen"
      intro={
        <p>
          Gib die E-Mail-Adresse deines Kontos ein. Wir schicken dir einen Link, mit dem du ein
          neues Passwort festlegst.
        </p>
      }
      footer={
        <p>
          Doch wieder eingefallen? <TextLink href="/konto/anmelden">Anmelden</TextLink>
        </p>
      }
    >
      <PasswordForgotten />
    </FormPage>
  );
}
