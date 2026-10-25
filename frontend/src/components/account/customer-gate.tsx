"use client";

import type { Route } from "next";
import type { ReactNode } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { PendingNotice } from "@/components/ui/pending-notice";
import type { AccountOut } from "@/lib/api/generated/model";
import { errorMessage } from "@/lib/i18n/problems";
import { CUSTOMER_AREA } from "@/lib/navigation";
import { useCustomerSession, useCustomerSessionCache } from "@/lib/session/customer";
import { useProtectedArea } from "@/lib/session/use-session-redirects";

export type CustomerDesk = {
  account: AccountOut;
  /** Forgets the session and navigates away (logout, account deletion). */
  leave: (target: Route) => void;
};

type CustomerGateProps = {
  /** What the loading notice says, e.g. "Deine Bestellungen werden geladen …". */
  pending: string;
  children: (desk: CustomerDesk) => ReactNode;
};

/**
 * Frame of the pages of "Mein Konto": the content appears once the API confirms the
 * customer session; visitors without one go to the login and come back afterwards.
 */
export function CustomerGate({ pending, children }: CustomerGateProps) {
  const session = useCustomerSession();
  const cache = useCustomerSessionCache();
  const { leave } = useProtectedArea(session, cache, CUSTOMER_AREA);

  switch (session.status) {
    case "loading":
    case "anonymous":
      return <PendingNotice className="mt-10">{pending}</PendingNotice>;
    case "error":
      return (
        <div className="mt-10 max-w-xl space-y-4">
          <Alert tone="danger" title="Dein Konto konnte nicht geladen werden">
            <p>{errorMessage(session.error)}</p>
          </Alert>
          <Button type="button" variant="secondary" onClick={() => void cache.revalidate()}>
            Erneut versuchen
          </Button>
        </div>
      );
    case "authenticated":
      return children({ account: session.account, leave });
  }
}
