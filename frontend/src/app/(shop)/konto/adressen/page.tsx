import type { Metadata } from "next";

import { AccountNav } from "@/components/account/account-nav";
import { AddressBook } from "@/components/account/address-book";
import { PageHeading } from "@/components/site/page-heading";

export const metadata: Metadata = {
  title: "Adressbuch",
};

export default function AddressBookPage() {
  return (
    <div className="mx-auto max-w-6xl px-5 py-14 sm:px-8 lg:py-20">
      <PageHeading caption="Mein Konto" title="Adressbuch" />
      <AccountNav className="mt-10" />
      <AddressBook />
    </div>
  );
}
