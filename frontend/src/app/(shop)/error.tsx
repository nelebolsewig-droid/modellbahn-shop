"use client";

import { useEffect } from "react";

import { PageHeading } from "@/components/site/page-heading";
import { Button } from "@/components/ui/button";

export default function ShopError({ error, retry }: { error: unknown; retry: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="mx-auto max-w-6xl px-5 py-16 sm:px-8 lg:py-24">
      <PageHeading caption="Störung" title="Etwas ist schiefgegangen">
        <p>Diese Seite konnte nicht angezeigt werden. Bitte versuche es gleich noch einmal.</p>
      </PageHeading>
      <Button type="button" onClick={retry} className="mt-8">
        Erneut versuchen
      </Button>
    </div>
  );
}
