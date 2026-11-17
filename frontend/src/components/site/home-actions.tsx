"use client";

import Link from "next/link";

import { Button } from "@/components/ui/button";
import { useCustomerSession } from "@/lib/session/customer";

/**
 * The calls to action on the start page: the catalogue first, then the account (a
 * logged-in customer goes to it instead of creating one).
 */
export function HomeActions() {
  const session = useCustomerSession();

  return (
    <div className="mt-10 flex animate-rise-in flex-wrap gap-3 [animation-delay:320ms]">
      <Button asChild variant="highlight" className="group">
        <Link href="/katalog">
          Zum Katalog
          <span aria-hidden="true" className="transition-transform duration-300 ease-settle group-hover:translate-x-1">
            →
          </span>
        </Link>
      </Button>
      {session.status === "authenticated" ? (
        <Button asChild variant="secondary">
          <Link href="/konto">Zu meinem Konto</Link>
        </Button>
      ) : (
        <Button asChild variant="secondary">
          <Link href="/konto/registrieren">Kundenkonto anlegen</Link>
        </Button>
      )}
    </div>
  );
}
