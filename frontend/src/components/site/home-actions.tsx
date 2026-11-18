"use client";

import Link from "next/link";

import { CatalogLink } from "@/components/shop/catalog-link";
import { Button } from "@/components/ui/button";
import { useCustomerSession } from "@/lib/session/customer";

/**
 * The calls to action on the start page: the catalogue first, then the account (a
 * logged-in customer goes to it instead of creating one).
 */
export function HomeActions() {
  const session = useCustomerSession();

  return (
    <div className="mt-10 flex flex-wrap gap-3">
      <Button asChild>
        <CatalogLink>Zu den Modellen</CatalogLink>
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
