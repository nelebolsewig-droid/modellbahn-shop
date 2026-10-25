/*
 * Numbers of the catalogue as German readers expect them: prices in euros with a
 * comma, lengths in millimetres, the readable product number.
 */

const LOCALE = "de-DE";

const priceFormat = new Intl.NumberFormat(LOCALE, { style: "currency", currency: "EUR" });
const decimalFormat = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 1 });
const integerFormat = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 });

/** 4990 → "49,90 €" */
export function formatPrice(cents: number): string {
  return priceFormat.format(cents / 100);
}

/** 112.5 → "112,5 mm" */
export function formatMillimetres(value: number): string {
  return `${decimalFormat.format(value)} mm`;
}

/** 1250 → "1.250 g" */
export function formatGrams(value: number): string {
  return `${integerFormat.format(value)} g`;
}

/** 42 → "MB-000042", the number on labels and invoices. */
export function formatProductNumber(value: number): string {
  return `MB-${String(value).padStart(6, "0")}`;
}

/** The technical line of a scale: ["H0", "1:87", "Gleis 16,5 mm"]; ["1:24"] for a road scale. */
export function scaleSpec(scale: { name: string; ratio: string; track_gauge_mm: number | null }): string[] {
  return [
    scale.name,
    ...(scale.name === scale.ratio ? [] : [scale.ratio]),
    ...(scale.track_gauge_mm === null ? [] : [`Gleis ${formatMillimetres(scale.track_gauge_mm)}`]),
  ];
}

/** "Länge 112,5 mm · Breite 64 mm" for whatever dimensions are known. */
export function dimensionsLine(dimensions: {
  length_mm: number | null;
  width_mm: number | null;
  height_mm: number | null;
}): string[] {
  const parts: string[] = [];
  if (dimensions.length_mm !== null) {
    parts.push(`L ${formatMillimetres(dimensions.length_mm)}`);
  }
  if (dimensions.width_mm !== null) {
    parts.push(`B ${formatMillimetres(dimensions.width_mm)}`);
  }
  if (dimensions.height_mm !== null) {
    parts.push(`H ${formatMillimetres(dimensions.height_mm)}`);
  }
  return parts;
}

/** Euro input of the admin area ("49,90", "49.9", "49") in cents; null if unreadable. */
export function parseEuroToCents(value: string): number | null {
  const normalised = value.trim().replace(/\s|€/g, "").replace(/\.(?=\d{3}(\D|$))/g, "").replace(",", ".");
  if (!/^\d+(\.\d{1,2})?$/.test(normalised)) {
    return null;
  }
  return Math.round(Number(normalised) * 100);
}

/** Cents as the admin area's euro input shows them: 4990 → "49,90". */
export function centsToEuroInput(cents: number): string {
  return (cents / 100).toFixed(2).replace(".", ",");
}
