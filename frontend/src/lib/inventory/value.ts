/*
 * The store's worth (Lagerwert) as the Stellwerk shows it: shares of the whole, the most
 * valuable models with the rest folded into one line. Pure, so it is tested without a browser.
 */

import type { ValueShareOut } from "@/lib/api/generated/model";

/** Models listed by name before the rest becomes "N weitere Modelle". */
export const MODELS_SHOWN = 5;

/** A share of the whole in percent, for the width of a bar: 0 to 100, never NaN. */
export function percentOf(part: number, whole: number): number {
  if (whole <= 0 || part <= 0) {
    return 0;
  }
  return Math.min(100, (part / whole) * 100);
}

export type ValueRow = ValueShareOut & { href: string | null };

/**
 * The most valuable models with a link to each, and the others in one line, so the list
 * stays short in a store with hundreds of models.
 */
export function topModels(models: readonly ValueShareOut[], shown = MODELS_SHOWN): { rows: ValueRow[]; rest: ValueShareOut | null } {
  const rows = models.slice(0, shown).map((model) => ({ ...model, href: `/admin/modelle/${model.key}` }));
  const others = models.slice(shown);
  if (others.length === 0) {
    return { rows, rest: null };
  }
  return {
    rows,
    rest: {
      key: "rest",
      name: others.length === 1 ? "1 weiteres Modell" : `${others.length} weitere Modelle`,
      pieces: others.reduce((sum, model) => sum + model.pieces, 0),
      value_cents: others.reduce((sum, model) => sum + model.value_cents, 0),
    },
  };
}

/** `1 Stück`, `12 Stück`: finished pieces. */
export function piecesWord(count: number): string {
  return `${new Intl.NumberFormat("de-DE").format(count)} Stück`;
}

/** `1 Teil`, `1.204 Teile`: printed parts. */
export function partsWord(count: number): string {
  return `${new Intl.NumberFormat("de-DE").format(count)} ${count === 1 ? "Teil" : "Teile"}`;
}
