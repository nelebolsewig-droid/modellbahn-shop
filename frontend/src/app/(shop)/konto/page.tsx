import type { Metadata } from "next";

import { AccountOverview } from "@/components/account/account-overview";
import { PageHeading } from "@/components/site/page-heading";

export const metadata: Metadata = {
  title: "Mein Konto",
};

export default function AccountPage() {
  return (
    <div className="mx-auto max-w-6xl px-5 py-14 sm:px-8 lg:py-20">
      <PageHeading caption="Kundenkonto" title="Mein Konto" />
      <AccountOverview />
    </div>
  );
}
