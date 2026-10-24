"use client";

import Link from "next/link";

import { Button } from "@/components/ui/button";
import { useCustomerSession } from "@/lib/session/customer";

/** The call to action on the start page; a logged-in customer goes to the account instead. */
export function HomeActions() {
  const session = useCustomerSession();

  if (session.status === "authenticated") {
    return (
      <div className="mt-10 flex flex-wrap gap-3">
        <Button asChild>
          <Link href="/konto">Zu meinem Konto</Link>
        </Button>
      </div>
    );
  }
  return (
    <div className="mt-10 flex flex-wrap gap-3">
      <Button asChild>
        <Link href="/konto/registrieren">Kundenkonto anlegen</Link>
      </Button>
      <Button asChild variant="secondary">
        <Link href="/konto/anmelden">Anmelden</Link>
      </Button>
    </div>
  );
}
