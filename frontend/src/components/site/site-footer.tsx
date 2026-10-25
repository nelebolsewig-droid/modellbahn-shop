import type { Route } from "next";
import Link from "next/link";

import { SHOP_NAME } from "@/lib/config";

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
      <div className="mx-auto flex max-w-6xl flex-col gap-4 px-5 py-8 text-small text-ink-tertiary sm:flex-row sm:items-center sm:justify-between sm:px-8">
        <p>{SHOP_NAME} · Modellbahn aus dem 3D-Drucker</p>
        <nav aria-label="Service und Rechtliches">
          <ul className="flex flex-wrap gap-x-6 gap-y-2">
            {LINKS.map((link) => (
              <li key={link.href}>
                <Link href={link.href} className="rounded-xs text-ink-secondary underline-offset-4 hover:text-ink hover:underline">
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </footer>
  );
}
