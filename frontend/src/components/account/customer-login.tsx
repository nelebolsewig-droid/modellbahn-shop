"use client";

import type { Route } from "next";

import { CredentialsForm } from "@/components/forms/credentials-form";
import { PendingNotice } from "@/components/ui/pending-notice";
import { TextLink } from "@/components/ui/text-link";
import { useLoginCustomer } from "@/lib/api/generated/store-account/store-account";
import { useCustomerSession, useCustomerSessionCache } from "@/lib/session/customer";
import { useRedirectWhenAuthenticated } from "@/lib/session/use-session-redirects";

function errorHelp(code: string) {
  if (code !== "email_not_verified") {
    return null;
  }
  return (
    <p>
      Link nicht mehr da?{" "}
      <TextLink href="/konto/bestaetigung-erneut">Bestätigungslink neu anfordern</TextLink>
    </p>
  );
}

/** Customer login; afterwards (or if already logged in) on to `returnTo`. */
export function CustomerLogin({ returnTo }: { returnTo: Route }) {
  const session = useCustomerSession();
  const cache = useCustomerSessionCache();
  const login = useLoginCustomer();
  useRedirectWhenAuthenticated(session, returnTo);

  if (session.status === "authenticated") {
    return <PendingNotice>Du bist angemeldet und wirst weitergeleitet …</PendingNotice>;
  }
  return (
    <CredentialsForm
      submitLabel="Anmelden"
      errorHelp={errorHelp}
      submit={async (values) => {
        // Storing the account switches the session to "authenticated", which redirects.
        cache.store(await login.mutateAsync({ data: values }));
      }}
    />
  );
}
