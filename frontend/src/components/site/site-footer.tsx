import type { Route } from "next";
import Link from "next/link";

import { SHOP_NAME } from "@/lib/config";

const WORKSHOP = [
  { href: "/termine", label: "Termine" },
  { href: "/ueber-uns", label: "Über uns" },
  { href: "/sonderanfertigung", label: "Sonderanfertigung" },
] as const satisfies readonly { href: Route; label: string }[];

const LINKS = [
  { href: "/versand", label: "Versand" },
  { href: "/agb", label: "AGB" },
  { href: "/widerruf", label: "Widerruf" },
  { href: "/impressum", label: "Impressum" },
  { href: "/datenschutz", label: "Datenschutz" },
] as const satisfies readonly { href: Route; label: string }[];

export function SiteFooter() {
  return (
    <footer className="mt-auto border-t border-line">
      <div className="mx-auto grid max-w-6xl gap-6 px-5 py-8 text-small text-ink-tertiary sm:px-8 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
        <p>{SHOP_NAME} · Fahrzeugmodelle in Handarbeit, seit 1992</p>
        <div className="flex flex-col gap-3 sm:flex-row sm:gap-10">
          <FooterLinks label="Werkstatt" links={WORKSHOP} />
          <FooterLinks label="Service und Rechtliches" links={LINKS} />
        </div>
      </div>
    </footer>
  );
}

function FooterLinks({ label, links }: { label: string; links: readonly { href: Route; label: string }[] }) {
  return (
    <nav aria-label={label}>
      <ul className="flex flex-wrap gap-x-6 gap-y-2">
        {links.map((link) => (
          <li key={link.href}>
            <Link href={link.href} className="rounded-xs text-ink-secondary underline-offset-4 hover:text-ink hover:underline">
              {link.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
