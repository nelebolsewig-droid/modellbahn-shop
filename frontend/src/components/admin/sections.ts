import type { Route } from "next";

import type { StaffRole } from "@/lib/api/generated/model";
import { OFFICE_ROLES } from "@/lib/staff";

const EVERYONE: ReadonlySet<StaffRole> = new Set(["owner", "staff", "packer"]);

/** The places of the Stellwerk that the navigation leads to. */
export type SectionKey =
  | "models"
  | "orders"
  | "scan"
  | "stock"
  | "overview"
  | "manufacturing"
  | "fairs"
  | "ebay"
  | "settings";

export type Section = { key: SectionKey; href: Route; label: string };

/**
 * Every place has its colour (ADR 0030): it tints the page, the active entry, the
 * primary buttons and the field codes while one is there. Values are design tokens.
 */
export const SECTION_COLORS: Readonly<Record<SectionKey, string>> = {
  overview: "var(--prussian-800)",
  models: "var(--highlight-fill)",
  orders: "var(--sky)",
  scan: "var(--highlight-fill)",
  stock: "var(--sea)",
  manufacturing: "var(--plum)",
  fairs: "var(--rose)",
  ebay: "var(--success)",
  settings: "var(--gray-700)",
};

const SECTIONS = {
  models: { href: "/admin/modelle", label: "Modelle", roles: OFFICE_ROLES },
  orders: { href: "/admin/bestellungen", label: "Bestellungen", roles: EVERYONE },
  scan: { href: "/admin/scanner", label: "Scannen", roles: EVERYONE },
  stock: { href: "/admin/lager", label: "Lager", roles: EVERYONE },
  overview: { href: "/admin", label: "Übersicht", roles: EVERYONE },
  manufacturing: { href: "/admin/fertigung", label: "Fertigung", roles: EVERYONE },
  fairs: { href: "/admin/messen", label: "Messen", roles: OFFICE_ROLES },
  ebay: { href: "/admin/ebay", label: "eBay", roles: OFFICE_ROLES },
  settings: { href: "/admin/einstellungen", label: "Einstellungen", roles: OFFICE_ROLES },
} as const satisfies Record<SectionKey, { href: Route; label: string; roles: ReadonlySet<StaffRole> }>;

/**
 * The header on a desk: the day's work (Modelle, Bestellungen, Lager) first, the rest
 * after it. Scannen is a button beside it, the Übersicht behind the Stellwerk's name.
 */
const HEADER_KEYS: readonly SectionKey[] = ["models", "orders", "stock", "manufacturing", "fairs", "ebay", "settings"];

/** The phone's bottom bar: the day's work, Scannen in the middle; the rest is behind "Mehr". */
const BAR_KEYS: readonly SectionKey[] = ["models", "orders", "scan", "stock"];
const MORE_KEYS: readonly SectionKey[] = ["overview", "manufacturing", "fairs", "ebay", "settings"];

/** Pages that live under another entry's address but belong to the settings. */
const SETTINGS_PATHS = ["/admin/einstellungen"];

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
