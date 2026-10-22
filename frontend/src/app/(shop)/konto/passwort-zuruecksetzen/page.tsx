import type { Metadata } from "next";

import { PasswordResetForm } from "@/components/account/password-reset-form";
import { FormPage } from "@/components/site/form-page";
import { firstParam } from "@/lib/search-params";

export const metadata: Metadata = {
  title: "Neues Passwort festlegen",
  // The one-time token is in the address; it must not travel on in a Referer header.
  referrer: "no-referrer",
};

export default async function PasswordResetPage({
  searchParams,
}: PageProps<"/konto/passwort-zuruecksetzen">) {
  const token = firstParam((await searchParams).token) || null;
  return (
    <FormPage
      caption="Kundenkonto"
      title="Neues Passwort"
      intro={<p>Lege ein neues Passwort für dein Konto fest. Danach meldest du dich damit an.</p>}
    >
      <PasswordResetForm token={token} />
    </FormPage>
  );
}
