import type { Metadata } from "next";

import { AdminShell } from "@/components/admin/admin-shell";
import { EbaySetupDesk } from "@/components/admin/marketplace/ebay-setup";
import { SettingsBackLink } from "@/components/admin/settings/settings-page";

export const metadata: Metadata = { title: "eBay-Einrichtung" };

/** `?ebay=verbunden` (or abgebrochen, ungueltig, fehler): the return from eBay's consent page. */
export default async function AdminEbaySetupPage({ searchParams }: PageProps<"/admin/einstellungen/ebay">) {
  const { ebay } = await searchParams;
  return (
    <AdminShell>
      <>
        <SettingsBackLink />
        <h1 className="mt-6 mb-8 text-heading sm:text-title">eBay-Einrichtung</h1>
        <EbaySetupDesk outcome={typeof ebay === "string" ? ebay : null} />
      </>
    </AdminShell>
  );
}
