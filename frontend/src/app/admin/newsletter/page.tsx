import type { Metadata } from "next";

import { AdminShell } from "@/components/admin/admin-shell";
import { NewsletterDesk } from "@/components/admin/newsletter/newsletter-desk";

export const metadata: Metadata = { title: "Newsletter" };

export default function AdminNewsletterPage() {
  return (
    <AdminShell>
      <>
        <p className="label-caps text-ink-tertiary">Auftritt</p>
        <h1 className="mt-4 mb-8 text-heading sm:text-title">Newsletter</h1>
        <NewsletterDesk />
      </>
    </AdminShell>
  );
}
