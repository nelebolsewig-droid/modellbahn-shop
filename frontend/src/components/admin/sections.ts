import type { Route } from "next";

import type { StaffRole } from "@/lib/api/generated/model";
import { OFFICE_ROLES } from "@/lib/staff";

const EVERYONE: ReadonlySet<StaffRole> = new Set(["owner", "staff", "packer"]);

/** The places of the Stellwerk that the navigation leads to. */
export type SectionKey =
  | "overview"
  | "orders"
  | "stock"
  | "manufacturing"
  | "scan"
  | "catalog"
  | "newModel"
  | "fairs"
  | "ebay"
  | "settings";

export type Section = { key: SectionKey; href: Route; label: string };

const SECTIONS = {
  overview: { href: "/admin", label: "Übersicht", roles: EVERYONE },
  orders: { href: "/admin/bestellungen", label: "Bestellungen", roles: EVERYONE },
  stock: { href: "/admin/lager", label: "Lager", roles: EVERYONE },
  manufacturing: { href: "/admin/fertigung", label: "Fertigung", roles: EVERYONE },
  scan: { href: "/admin/scanner", label: "Scannen", roles: EVERYONE },
  catalog: { href: "/admin/katalog", label: "Katalog", roles: OFFICE_ROLES },
  newModel: { href: "/admin/erfassen", label: "Neues Modell", roles: OFFICE_ROLES },
  fairs: { href: "/admin/messen", label: "Messen", roles: OFFICE_ROLES },
  ebay: { href: "/admin/ebay", label: "eBay", roles: OFFICE_ROLES },
  settings: { href: "/admin/einstellungen", label: "Einstellungen", roles: OFFICE_ROLES },
} as const satisfies Record<SectionKey, { href: Route; label: string; roles: ReadonlySet<StaffRole> }>;

/** The header on a desk: the day's work first, the settings last. Scannen is a button beside it. */
const HEADER_KEYS: readonly SectionKey[] = [
  "overview",
  "orders",
  "stock",
  "manufacturing",
  "catalog",
  "fairs",
  "ebay",
  "settings",
];

/** The phone's bottom bar, with Scannen in the middle; the rest is behind "Mehr". */
const BAR_KEYS: readonly SectionKey[] = ["overview", "orders", "scan", "stock"];
const MORE_KEYS: readonly SectionKey[] = ["manufacturing", "catalog", "newModel", "fairs", "ebay", "settings"];

/** Pages that live under another entry's address but belong to the settings. */
const SETTINGS_PATHS = ["/admin/einstellungen", "/admin/katalog/kategorien", "/admin/katalog/massstaebe"];

export function mayOpen(role: StaffRole, key: SectionKey): boolean {
  return SECTIONS[key].roles.has(role);
}

export function section(key: SectionKey): Section {
  const { href, label } = SECTIONS[key];
  return { key, href, label };
}

function sectionsFor(role: StaffRole, keys: readonly SectionKey[]): Section[] {
  return keys.filter((key) => mayOpen(role, key)).map(section);
}

export function headerSections(role: StaffRole): Section[] {
  return sectionsFor(role, HEADER_KEYS);
}

export function barSections(role: StaffRole): Section[] {
  return sectionsFor(role, BAR_KEYS);
}

export function moreSections(role: StaffRole): Section[] {
  return sectionsFor(role, MORE_KEYS);
}

function within(pathname: string, prefix: string): boolean {
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

/** The entry a page belongs to, for highlighting it; null for pages outside the navigation. */
export function activeSection(pathname: string): SectionKey | null {
  if (pathname === "/admin") {
    return "overview";
  }
  if (SETTINGS_PATHS.some((prefix) => within(pathname, prefix))) {
    return "settings";
  }
  const match = (Object.keys(SECTIONS) as SectionKey[]).find(
    (key) => key !== "overview" && within(pathname, SECTIONS[key].href),
  );
  return match ?? null;
}
