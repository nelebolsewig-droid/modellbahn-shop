"use client";

import Link from "next/link";

import { Button } from "@/components/ui/button";
import { useCustomerSession } from "@/lib/session/customer";

/** "Anmelden" or "Mein Konto", depending on what the API says about the session. */
export function AccountLink() {
  const session = useCustomerSession();

  if (session.status === "loading") {
    // Keeps the header from jumping when the answer arrives.
    return <span className="inline-block h-9 w-32" aria-hidden="true" />;
  }
  if (session.status === "authenticated") {
    return (
      <Button asChild variant="secondary" size="sm">
        <Link href="/konto">Mein Konto</Link>
      </Button>
    );
  }
  return (
    <Button asChild variant="secondary" size="sm">
      <Link href="/konto/anmelden">Anmelden</Link>
    </Button>
  );
}
