import type { Route } from "next";
import Link from "next/link";

import { CartLink } from "@/components/shop/cart-link";
import { CatalogLink } from "@/components/shop/catalog-link";
import { DecalsLink } from "@/components/shop/decals-link";
import { SHOP_NAME } from "@/lib/config";
import { cn } from "@/lib/utils";

import { AccountLink } from "./account-link";
import { Wordmark } from "./wordmark";

// On phones only the catalogue fits beside the wordmark, cart and account (at 390 px "Termine"
// pushed the header past the screen); "Termine" is also in the footer.
const SECTIONS = [
  { href: "/katalog", label: "Modelle", narrow: true },
  { href: "/decals", label: "Decals", narrow: true },
  { href: "/projekte", label: "Projekte", narrow: false },
  { href: "/termine", label: "Termine", narrow: false },
] as const satisfies readonly { href: Route; label: string; narrow: boolean }[];

export function SiteHeader() {
  return (
    <header className="relative z-20 h-(--site-header-height) border-b border-line">
      <div className="mx-auto flex h-full max-w-6xl items-center justify-between gap-2 px-4 sm:gap-4 sm:px-8">
        {/* Phones need the width for catalogue, cart and account, so the wordmark is smaller there. */}
        <Link href="/" className="shrink-0">
          <Wordmark name={SHOP_NAME} className="text-[0.9375rem] sm:text-[1.625rem]" />
        </Link>
        <div className="flex items-center gap-1 sm:gap-6">
          <nav aria-label="Shop" className="flex items-center">
            {SECTIONS.map((section) => {
              const className = cn(
                "px-1 py-1 text-small font-medium text-ink-secondary hover:text-ink sm:px-2 sm:text-[0.9375rem]",
                !section.narrow && "max-sm:hidden",
              );
              // The catalogue opens in the scale browsed last.
              return section.href === "/katalog" ? (
                <CatalogLink key={section.href} className={className}>
                  {section.label}
                </CatalogLink>
              ) : section.href === "/decals" ? (
                <DecalsLink key={section.href} className={className}>
                  {section.label}
                </DecalsLink>
              ) : (
                <Link key={section.href} href={section.href} className={className}>
                  {section.label}
                </Link>
              );
            })}
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
