import Link from "next/link";

import { SHOP_NAME } from "@/lib/config";

export function SiteFooter() {
  return (
    <footer className="mt-auto border-t border-line">
      <div className="mx-auto flex max-w-6xl flex-col gap-4 px-5 py-8 text-small text-ink-tertiary sm:flex-row sm:items-center sm:justify-between sm:px-8">
        <p>{SHOP_NAME} · Modellbahn aus dem 3D-Drucker</p>
        <nav aria-label="Rechtliches">
          <ul className="flex gap-6">
            <li>
              <Link href="/impressum" className="rounded-xs text-ink-secondary underline-offset-4 hover:text-ink hover:underline">
                Impressum
              </Link>
            </li>
            <li>
              <Link href="/datenschutz" className="rounded-xs text-ink-secondary underline-offset-4 hover:text-ink hover:underline">
                Datenschutz
              </Link>
            </li>
          </ul>
        </nav>
      </div>
    </footer>
  );
}
