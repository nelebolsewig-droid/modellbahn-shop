import Link from "next/link";

import { SHOP_NAME } from "@/lib/config";

export function SiteFooter() {
  return (
    <footer className="mt-auto">
      <div className="track-rule" aria-hidden="true" />
      <div className="mx-auto flex max-w-6xl flex-col gap-4 px-5 py-8 sm:flex-row sm:items-center sm:justify-between sm:px-8">
        <p className="label-caps text-ink-muted">{SHOP_NAME} · Modellbahn aus dem 3D-Drucker</p>
        <nav aria-label="Rechtliches">
          <ul className="flex gap-6 text-sm">
            <li>
              <Link href="/impressum" className="rounded-xs underline-offset-4 hover:underline">
                Impressum
              </Link>
            </li>
            <li>
              <Link href="/datenschutz" className="rounded-xs underline-offset-4 hover:underline">
                Datenschutz
              </Link>
            </li>
          </ul>
        </nav>
      </div>
    </footer>
  );
}
