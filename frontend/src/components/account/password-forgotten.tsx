"use client";

import { EmailRequestForm } from "@/components/forms/email-request-form";
import { ResultPanel } from "@/components/forms/result-panel";
import { useRequestPasswordReset } from "@/lib/api/generated/store-account/store-account";

export function PasswordForgotten() {
  const reset = useRequestPasswordReset();
  return (
    <EmailRequestForm
      submitLabel="Link zum Zurücksetzen senden"
      submit={async (values) => {
        await reset.mutateAsync({ data: values });
      }}
      renderResult={(email) => (
        // Same answer for every address: whether it has an account stays private.
        <ResultPanel tone="success" title="Anfrage angekommen">
          <p>
            Wenn zu <strong className="break-all">{email}</strong> ein Konto gehört, schicken wir
            dir einen Link, mit dem du ein neues Passwort festlegst. Er ist eine Stunde gültig.
          </p>
        </ResultPanel>
      )}
    />
  );
}
