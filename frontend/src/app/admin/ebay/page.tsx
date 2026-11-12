import type { Metadata, Route } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { AdminShell } from "@/components/admin/admin-shell";
import { EbayDesk } from "@/components/admin/marketplace/ebay-desk";
import { Button } from "@/components/ui/button";
import { EBAY_SETUP_HREF } from "@/lib/marketplace/labels";

export const metadata: Metadata = { title: "eBay" };

/**
 * `?ebay=verbunden` (or abgebrochen, ungueltig, fehler): the return from eBay's consent
 * page, which the backend sends here. Connecting is part of the setup, so it goes on there.
 */
export default async function AdminEbayPage({ searchParams }: PageProps<"/admin/ebay">) {
  const { ebay } = await searchParams;
  if (typeof ebay === "string") {
    redirect(`${EBAY_SETUP_HREF}?ebay=${encodeURIComponent(ebay)}` as Route);
  }
  return (
    <AdminShell>
      <>
        <p className="label-caps text-ink-tertiary">Zweiter Verkaufsweg</p>
        <div className="mt-4 mb-8 flex flex-wrap items-end justify-between gap-4">
          <h1 className="text-heading sm:text-title">eBay</h1>
          <Button asChild size="sm" variant="ghost">
            <Link href={EBAY_SETUP_HREF}>Einrichtung</Link>
          </Button>
        </div>
        <EbayDesk />
      </>
    </AdminShell>
  );
}
