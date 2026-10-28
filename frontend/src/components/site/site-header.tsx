import type { Route } from "next";
import Link from "next/link";

import { CartLink } from "@/components/shop/cart-link";
import { SHOP_NAME } from "@/lib/config";

import { AccountLink } from "./account-link";
import { LogoMark } from "./logo-mark";

const SECTIONS = [
  { href: "/katalog", label: "Katalog" },
  { href: "/termine", label: "Termine" },
] as const satisfies readonly { href: Route; label: string }[];

export function SiteHeader() {
  return (
    <header className="border-b border-line">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-5 py-4 sm:px-8">
        <Link href="/" className="flex min-w-0 items-center gap-3 rounded-sm">
          <LogoMark />
          {/* Phones need the width for catalogue, cart and account; the name stays for screen readers. */}
          <span className="sr-only text-[1.0625rem] font-medium tracking-[-0.01em] sm:not-sr-only">{SHOP_NAME}</span>
        </Link>
        <div className="flex items-center gap-2 sm:gap-6">
          <nav aria-label="Shop" className="flex items-center">
            {SECTIONS.map((section) => (
              <Link
                key={section.href}
                href={section.href}
                className="rounded-sm px-2 py-1 text-[0.9375rem] font-medium text-ink-secondary hover:text-ink"
              >
                {section.label}
              </Link>
            ))}
          </nav>
          <CartLink />
          <nav aria-label="Kundenkonto">
            <AccountLink />
          </nav>
        </div>
      </div>
    </header>
  );
}
