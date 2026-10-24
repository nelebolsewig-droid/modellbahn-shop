import Link from "next/link";

import { SHOP_NAME } from "@/lib/config";

import { AccountLink } from "./account-link";
import { LogoMark } from "./logo-mark";

export function SiteHeader() {
  return (
    <header className="border-b border-line">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-5 py-4 sm:px-8">
        <Link href="/" className="flex items-center gap-3 rounded-sm">
          <LogoMark />
          <span className="text-[1.0625rem] font-medium tracking-[-0.01em]">{SHOP_NAME}</span>
        </Link>
        <div className="flex items-center gap-2 sm:gap-6">
          <nav aria-label="Shop">
            <Link
              href="/katalog"
              className="rounded-sm px-2 py-1 text-[0.9375rem] font-medium text-ink-secondary hover:text-ink"
            >
              Katalog
            </Link>
          </nav>
          <nav aria-label="Kundenkonto">
            <AccountLink />
          </nav>
        </div>
      </div>
    </header>
  );
}
