import type { Route } from "next";
import Link from "next/link";

import { SHOP_NAME } from "@/lib/config";

const WORKSHOP = [
  { href: "/termine", label: "Termine" },
  { href: "/ueber-uns", label: "Über uns" },
  { href: "/so-entsteht-ein-modell", label: "So entsteht ein Modell" },
  { href: "/sonderanfertigung", label: "Sonderanfertigung" },
] as const satisfies readonly FooterLink[];

// "Vertrag widerrufen" is the withdrawal function (§ 356a BGB): on every page, and set off.
const LINKS = [
  { href: "/versand", label: "Versand" },
  { href: "/agb", label: "AGB" },
  { href: "/widerruf", label: "Widerrufsbelehrung" },
  { href: "/widerruf/erklaeren", label: "Vertrag widerrufen", strong: true },
  { href: "/impressum", label: "Impressum" },
  { href: "/datenschutz", label: "Datenschutz" },
] as const satisfies readonly FooterLink[];

type FooterLink = { href: Route; label: string; strong?: boolean };

export function SiteFooter() {
  return (
    <footer className="mt-auto bg-night text-on-night-muted">
      <div aria-hidden="true" className="h-1 bg-spectrum" />
      <div className="mx-auto grid max-w-6xl gap-6 px-5 py-10 text-small sm:px-8 lg:grid-cols-[minmax(14rem,1fr)_auto] lg:items-center">
        <p>
          <span className="font-medium text-on-night">{SHOP_NAME}</span> · Fahrzeugmodelle in Handarbeit, seit 1992
        </p>
        <div className="flex flex-col gap-3 sm:flex-row sm:gap-10">
          <FooterLinks label="Werkstatt" links={WORKSHOP} />
          <FooterLinks label="Service und Rechtliches" links={LINKS} />
        </div>
      </div>
    </footer>
  );
}

function FooterLinks({ label, links }: { label: string; links: readonly FooterLink[] }) {
  return (
    <nav aria-label={label}>
      <ul className="flex flex-wrap gap-x-6 gap-y-2">
        {links.map((link) => (
          <li key={link.href}>
            <Link
              href={link.href}
              className={
                link.strong
                  ? "rounded-xs font-medium text-sun underline underline-offset-4 outline-on-night hover:text-on-night"
                  : "rounded-xs underline-offset-4 outline-on-night hover:text-on-night hover:underline"
              }
            >
              {link.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
