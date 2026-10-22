"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import { ResultPanel } from "@/components/forms/result-panel";
import { PendingNotice } from "@/components/ui/pending-notice";
import { TextLink } from "@/components/ui/text-link";
import { useVerifyCustomerEmail } from "@/lib/api/generated/store-account/store-account";
import { errorMessage } from "@/lib/i18n/problems";
import { CUSTOMER_AREA } from "@/lib/navigation";
import { useCustomerSessionCache } from "@/lib/session/customer";

/**
 * Redeems the token from the verification e-mail. Success logs the customer in
 * (the API sets the session cookie) and leads to "Mein Konto".
 */
export function VerifyEmail({ token }: { token: string | null }) {
  const router = useRouter();
  const cache = useCustomerSessionCache();
  const { mutate, status, error } = useVerifyCustomerEmail({
    mutation: {
      onSuccess(account) {
        cache.store(account);
        router.replace(CUSTOMER_AREA.home);
      },
    },
  });
  // A token works once. Development mode runs effects twice; this keeps it to one request.
  const requested = useRef<string | null>(null);

  useEffect(() => {
    if (token === null || requested.current === token) {
      return;
    }
    requested.current = token;
    mutate({ data: { token } });
  }, [token, mutate]);

  if (token === null) {
    return (
      <ResultPanel tone="danger" title="Der Link ist unvollständig">
        <p>Bitte öffne den Link direkt aus der E-Mail. Wenn das nicht klappt, schicken wir dir einen neuen.</p>
        <p>
          <TextLink href="/konto/bestaetigung-erneut">Neuen Bestätigungslink anfordern</TextLink>
        </p>
      </ResultPanel>
    );
  }
  if (status === "error") {
    return (
      <ResultPanel tone="danger" title="Das hat nicht geklappt">
        <p>{errorMessage(error)}</p>
        <p>
          <TextLink href="/konto/bestaetigung-erneut">Neuen Bestätigungslink anfordern</TextLink>
        </p>
      </ResultPanel>
    );
  }
  if (status === "success") {
    return (
      <ResultPanel tone="success" title="E-Mail-Adresse bestätigt">
        <p>Willkommen! Du bist jetzt angemeldet und wirst zu deinem Konto weitergeleitet.</p>
        <p>
          <TextLink href={CUSTOMER_AREA.home}>Weiter zu „Mein Konto“</TextLink>
        </p>
      </ResultPanel>
    );
  }
  return <PendingNotice>Wir bestätigen deine E-Mail-Adresse …</PendingNotice>;
}
