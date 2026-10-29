import type { Metadata } from "next";

import { AdminShell } from "@/components/admin/admin-shell";
import { EbayDesk } from "@/components/admin/marketplace/ebay-desk";

export const metadata: Metadata = { title: "eBay" };

/** `?ebay=verbunden` (or abgebrochen, ungueltig, fehler): the return from eBay's consent page. */
export default async function AdminEbayPage({ searchParams }: PageProps<"/admin/ebay">) {
  const { ebay } = await searchParams;
  return (
    <AdminShell>
      <>
        <p className="label-caps text-ink-tertiary">Zweiter Verkaufsweg</p>
        <h1 className="mt-4 mb-8 text-heading sm:text-title">eBay</h1>
        <EbayDesk outcome={typeof ebay === "string" ? ebay : null} />
      </>
    </AdminShell>
  );
}
