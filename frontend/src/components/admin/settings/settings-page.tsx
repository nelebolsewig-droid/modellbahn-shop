"use client";

import type { Route } from "next";
import Link from "next/link";

import { AdminShell } from "@/components/admin/admin-shell";
import { OFFICE_ROLES } from "@/lib/staff";

const SETTINGS_HREF = "/admin/einstellungen" satisfies Route;

/** What is set up once and seldom changed, away from the day's work. */
const ENTRIES = [
  {
    code: "EIN 01",
    href: "/admin/katalog/kategorien",
    title: "Kategorien",
    text: "Wie der Katalog geordnet ist, z. B. Straßenfahrzeuge, LKW, Feuerwehr.",
  },
  {
    code: "EIN 02",
    href: "/admin/katalog/massstaebe",
    title: "Maßstäbe",
    text: "Welche Maßstäbe der Shop führt, mit Verhältnis und Spurweite.",
  },
  {
    code: "EIN 03",
    href: "/admin/einstellungen/ebay",
    title: "eBay-Einrichtung",
    text: "Verbindung, Versand und Zahlung, eBay-Kategorien und Löschmeldungen. Ändern kann sie nur der Inhaber.",
  },
] as const satisfies readonly { code: string; href: Route; title: string; text: string }[];

export function SettingsPage() {
  return (
    <AdminShell>
      {({ staff }) => (
        <>
          <p className="label-caps text-ink-tertiary">Stellwerk</p>
          <h1 className="mt-4 mb-8 text-heading sm:text-title">Einstellungen</h1>
          {OFFICE_ROLES.has(staff.role) ? (
            <SettingsOverview />
          ) : (
            <p className="text-small text-ink-secondary">Die Einstellungen pflegen Inhaber und Mitarbeiter.</p>
          )}
        </>
      )}
    </AdminShell>
  );
}

/** One card per setting, each leading to its page. */
export function SettingsOverview() {
  return (
    <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {ENTRIES.map((entry) => (
        <li key={entry.href}>
          <Link
            href={entry.href}
            className="group flex h-full flex-col rounded-md border border-line bg-surface p-5 transition-colors hover:border-ink"
          >
            <span aria-hidden="true" className="font-mono text-hint text-ink-tertiary">
              {entry.code}
            </span>
            <span className="mt-3 text-body-lg font-medium">{entry.title}</span>
            <span className="mt-1 text-small text-ink-secondary">{entry.text}</span>
            <span aria-hidden="true" className="mt-4 text-small font-medium text-accent group-hover:underline">
              Öffnen →
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

/** Above a page that belongs to the settings. */
export function SettingsBackLink() {
  return (
    <Link
      href={SETTINGS_HREF}
      className="inline-flex items-center gap-2 text-small font-medium text-ink-secondary hover:text-ink"
    >
      <span aria-hidden="true">←</span> Einstellungen
    </Link>
  );
}
