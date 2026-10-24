"use client";

import { EmailRequestForm } from "@/components/forms/email-request-form";
import { ResultPanel } from "@/components/forms/result-panel";
import { useResendVerificationEmail } from "@/lib/api/generated/store-account/store-account";

export function ResendVerification() {
  const resend = useResendVerificationEmail();
  return (
    <EmailRequestForm
      submitLabel="Link senden"
      submit={async (values) => {
        await resend.mutateAsync({ data: values });
      }}
      renderResult={(email) => (
        // Same answer for every address: whether it has an unverified account stays private.
        <ResultPanel tone="success" title="Anfrage angekommen">
          <p>
            Wenn zu <strong className="break-all">{email}</strong> ein Konto gehört, das noch nicht
            bestätigt ist, ist ein neuer Link unterwegs. Er ist 24 Stunden gültig.
          </p>
        </ResultPanel>
      )}
    />
  );
}
