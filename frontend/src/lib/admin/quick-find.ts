import type { Route } from "next";

import type { StaffRole } from "@/lib/api/generated/model";
import { OFFICE_ROLES } from "@/lib/staff";

/*
 * The Stellwerk's quick search (⌘K, ADR 0033): one field that finds a page, an action,
 * an order by its number, e-mail or name, and a model by its name. The pages and actions
 * are known here; orders and models come from the API as one types.
 */

export type Shortcut = { href: Route; label: string; hint: string; words: string; officeOnly?: boolean };

export const SHORTCUTS: readonly Shortcut[] = [
  { href: "/admin", label: "Heute", hint: "Was als Nächstes dran ist", words: "start übersicht tag aufgaben dashboard" },
  { href: "/admin/bestellungen", label: "Bestellungen", hint: "Übersicht von Eingang bis Paket", words: "aufträge verkauf orders pakete versand" },
  { href: "/admin/scanner", label: "Scannen", hint: "Etikett oder Platz scannen", words: "scanner kamera etikett barcode qr einbuchen nachschlagen" },
  { href: "/admin/modelle", label: "Modelle", hint: "Alle Modelle im Katalog", words: "katalog produkte artikel", officeOnly: true },
  { href: "/admin/modelle/neu", label: "Neues Modell anlegen", hint: "In vier Schritten, auch wie ein vorhandenes", words: "anlegen erstellen produkt hinzufügen neu", officeOnly: true },
  { href: "/admin/lager", label: "Lager", hint: "Was wo liegt", words: "bestand regal stücke inventur" },
  { href: "/admin/fertigung", label: "Fertigung", hint: "Drucker, Druckplatten und was zu fertigen ist", words: "drucker druckerhalle 3d druck werkstatt platte" },
  { href: "/admin/fertigung/teile", label: "Teile und Stücklisten", hint: "Woraus ein Modell besteht", words: "teile stückliste bauteile bom" },
  { href: "/admin/messen", label: "Messen", hint: "Verkauf am Stand", words: "messe markt stand kasse", officeOnly: true },
  { href: "/admin/newsletter", label: "Newsletter", hint: "Wer ihn bekommt, wann der nächste kommt", words: "newsletter rundbrief mail empfehlungen abonnenten", officeOnly: true },
  { href: "/admin/ebay", label: "eBay", hint: "Angebote und Bestellungen von eBay", words: "marktplatz angebote", officeOnly: true },
  { href: "/admin/einstellungen", label: "Einstellungen", hint: "Was selten geändert wird", words: "konfiguration setup", officeOnly: true },
  { href: "/admin/einstellungen/kategorien", label: "Kategorien", hint: "Wie der Katalog geordnet ist", words: "kategorie ordnung", officeOnly: true },
  { href: "/admin/einstellungen/massstaebe", label: "Maßstäbe", hint: "H0, TT, N und die anderen", words: "massstab spur h0 tt n", officeOnly: true },
  { href: "/admin/einstellungen/lieferzeit", label: "Lieferzeit", hint: "Wie lange das Nachfertigen dauert", words: "wochen dauer nachfertigen", officeOnly: true },
];

function fold(text: string): string {
  return text
    .toLocaleLowerCase("de")
    .replaceAll("ß", "ss")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "");
}

/** The shortcuts a role may open that fit the query, best first; all of them for an empty query. */
export function findShortcuts(query: string, role: StaffRole): Shortcut[] {
  const allowed = SHORTCUTS.filter((entry) => !entry.officeOnly || OFFICE_ROLES.has(role));
  const words = fold(query).split(/\s+/).filter(Boolean);
  if (words.length === 0) {
    return allowed.slice(0, 6);
  }
  const scored = allowed.flatMap((entry) => {
    const label = fold(entry.label);
    const haystack = `${label} ${fold(entry.hint)} ${fold(entry.words)}`;
    if (!words.every((word) => haystack.includes(word))) {
      return [];
    }
    const score = words.reduce((sum, word) => sum + (label.startsWith(word) ? 3 : label.includes(word) ? 2 : 1), 0);
    return [{ entry, score }];
  });
  return scored.sort((a, b) => b.score - a.score).map(({ entry }) => entry);
}

/** Looks like part of an order number ("MB-2026-00012", "00012", "12"): orders first then. */
export function looksLikeOrderNumber(query: string): boolean {
  return /^(mb-?)?[\d-]{2,}$/i.test(query.trim());
}
