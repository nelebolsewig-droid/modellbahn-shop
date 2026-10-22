import type { Metadata } from "next";
import Link from "next/link";

import { PageHeading } from "@/components/site/page-heading";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = {
  title: "Konto gelöscht",
};

export default function AccountDeletedPage() {
  return (
    <div className="mx-auto max-w-6xl px-5 py-12 sm:px-8 lg:py-20">
      <PageHeading caption="Kundenkonto" title="Dein Konto ist gelöscht">
        <p>
          Wir haben deinen Namen, deine E-Mail-Adresse und dein Passwort entfernt und dich auf allen
          Geräten abgemeldet. Wenn du wiederkommen möchtest, kannst du jederzeit ein neues Konto
          anlegen.
        </p>
      </PageHeading>
      <Button asChild className="mt-8">
        <Link href="/">Zur Startseite</Link>
      </Button>
    </div>
  );
}
