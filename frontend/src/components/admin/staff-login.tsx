"use client";

import type { Route } from "next";

import { CredentialsForm } from "@/components/forms/credentials-form";
import { PendingNotice } from "@/components/ui/pending-notice";
import { useStaffLogin } from "@/lib/api/generated/admin-auth/admin-auth";
import { useStaffSession, useStaffSessionCache } from "@/lib/session/staff";
import { useRedirectWhenAuthenticated } from "@/lib/session/use-session-redirects";

/** Staff login; afterwards (or if already logged in) on to `returnTo`. */
export function StaffLogin({ returnTo }: { returnTo: Route }) {
  const session = useStaffSession();
  const cache = useStaffSessionCache();
  const login = useStaffLogin();
  useRedirectWhenAuthenticated(session, returnTo);

  if (session.status === "authenticated") {
    return <PendingNotice>Angemeldet. Das Stellwerk wird geöffnet …</PendingNotice>;
  }
  return (
    <CredentialsForm
      submitLabel="Anmelden"
      submit={async (values) => {
        // Storing the account switches the session to "authenticated", which redirects.
        cache.store(await login.mutateAsync({ data: values }));
      }}
    />
  );
}
