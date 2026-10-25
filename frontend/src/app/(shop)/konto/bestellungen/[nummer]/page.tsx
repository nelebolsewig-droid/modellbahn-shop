import type { Metadata } from "next";

import { AccountNav } from "@/components/account/account-nav";
import { MyOrder } from "@/components/account/my-order";

export async function generateMetadata({ params }: PageProps<"/konto/bestellungen/[nummer]">): Promise<Metadata> {
  const { nummer } = await params;
  return { title: `Bestellung ${decodeURIComponent(nummer)}` };
}

export default async function MyOrderPage({ params }: PageProps<"/konto/bestellungen/[nummer]">) {
  const { nummer } = await params;
  return (
    <div className="mx-auto max-w-6xl px-5 py-14 sm:px-8 lg:py-20">
      <AccountNav className="mb-10" />
      <MyOrder number={decodeURIComponent(nummer)} />
    </div>
  );
}
