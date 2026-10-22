import type { Metadata } from "next";
import Link from "next/link";

import { StaffLogin } from "@/components/admin/staff-login";
import { LogoMark } from "@/components/site/logo-mark";
import { SignalLamp } from "@/components/ui/signal-lamp";
import { SHOP_NAME } from "@/lib/config";
import { RETURN_TO_PARAM, safeReturnPath, STAFF_AREA } from "@/lib/navigation";
import { firstParam } from "@/lib/search-params";

export const metadata: Metadata = {
  title: "Anmelden",
};

export default async function StaffLoginPage({ searchParams }: PageProps<"/admin/anmelden">) {
  const returnTo = safeReturnPath(firstParam((await searchParams)[RETURN_TO_PARAM]), STAFF_AREA);
  return (
    <main className="grid min-h-dvh place-items-center px-5 py-12">
      <div className="w-full max-w-md">
        <div className="flex items-center gap-3">
          <LogoMark />
          <p className="label-caps text-ink-muted">{SHOP_NAME} · Stellwerk</p>
        </div>
        <h1 className="mt-8 text-5xl">Anmelden</h1>
        <p className="mt-3 leading-7 text-ink-muted">
          Zugang für das Team. Eine Selbstregistrierung gibt es nicht; Zugänge legt die Inhaberin
          oder der Inhaber an.
        </p>
        <div className="mt-8 rule rounded-md border-line-strong bg-surface-raised">
          <div className="flex items-center gap-2 rule-b border-line px-6 py-3">
            <SignalLamp color="red" />
            <p className="label-caps text-ink-muted">Fahrstraße gesperrt bis zur Anmeldung</p>
          </div>
          <div className="p-6">
            <StaffLogin returnTo={returnTo} />
          </div>
        </div>
        <p className="mt-6 text-sm">
          <Link href="/" className="rounded-xs text-ink-muted underline-offset-4 hover:text-ink hover:underline">
            Zurück zum Shop
          </Link>
        </p>
      </div>
    </main>
  );
}
