"use client";

import { useEffect } from "react";

import { Button } from "@/components/ui/button";

export default function AdminError({ error, retry }: { error: unknown; retry: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <main className="mx-auto max-w-3xl px-5 py-16 sm:px-8">
      <p className="label-caps text-danger">Störung</p>
      <h1 className="mt-4 text-title">Etwas ist schiefgegangen</h1>
      <p className="mt-4 text-ink-secondary">
        Diese Ansicht konnte nicht angezeigt werden. Bitte versuche es gleich noch einmal.
      </p>
      <Button type="button" onClick={retry} className="mt-8">
        Erneut versuchen
      </Button>
    </main>
  );
}
