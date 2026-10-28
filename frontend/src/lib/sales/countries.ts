/*
 * The countries the shop ships to, mirrored from the sales module
 * (backend/src/modellbahn/modules/sales/domain/model.py, SHIPPING_ZONES): Germany first,
 * then the rest of the EU by German name. The rates come from the API; this list gives
 * the address form its choices and checks postal codes before anything is sent.
 */

export const SHIPPING_COUNTRY_LIST = [
  { code: "DE", name: "Deutschland", postal: /^\d{5}$/, example: "38707" },
  { code: "BE", name: "Belgien", postal: /^\d{4}$/, example: "1000" },
  { code: "BG", name: "Bulgarien", postal: /^\d{4}$/, example: "1000" },
  { code: "DK", name: "Dänemark", postal: /^\d{4}$/, example: "1050" },
  { code: "EE", name: "Estland", postal: /^\d{5}$/, example: "10111" },
  { code: "FI", name: "Finnland", postal: /^\d{5}$/, example: "00100" },
  { code: "FR", name: "Frankreich", postal: /^\d{5}$/, example: "75001" },
  { code: "GR", name: "Griechenland", postal: /^\d{3} ?\d{2}$/, example: "105 57" },
  { code: "IE", name: "Irland", postal: /^(?:[AC-FHKNPRTV-Y]\d{2}|D6W) ?[0-9AC-FHKNPRTV-Y]{4}$/, example: "D02 X285" },
  { code: "IT", name: "Italien", postal: /^\d{5}$/, example: "00118" },
  { code: "HR", name: "Kroatien", postal: /^\d{5}$/, example: "10000" },
  { code: "LV", name: "Lettland", postal: /^(?:LV-)?\d{4}$/, example: "LV-1050" },
  { code: "LT", name: "Litauen", postal: /^(?:LT-)?\d{5}$/, example: "LT-01100" },
  { code: "LU", name: "Luxemburg", postal: /^(?:L-)?\d{4}$/, example: "L-1450" },
  { code: "MT", name: "Malta", postal: /^[A-Z]{3} ?\d{2,4}$/, example: "VLT 1117" },
  { code: "NL", name: "Niederlande", postal: /^\d{4} ?[A-Z]{2}$/, example: "1012 AB" },
  { code: "AT", name: "Österreich", postal: /^\d{4}$/, example: "1010" },
  { code: "PL", name: "Polen", postal: /^\d{2}-\d{3}$/, example: "00-950" },
  { code: "PT", name: "Portugal", postal: /^\d{4}-\d{3}$/, example: "1100-148" },
  { code: "RO", name: "Rumänien", postal: /^\d{6}$/, example: "010011" },
  { code: "SE", name: "Schweden", postal: /^\d{3} ?\d{2}$/, example: "114 55" },
  { code: "SK", name: "Slowakei", postal: /^\d{3} ?\d{2}$/, example: "811 01" },
  { code: "SI", name: "Slowenien", postal: /^(?:SI-)?\d{4}$/, example: "1000" },
  { code: "ES", name: "Spanien", postal: /^\d{5}$/, example: "28001" },
  { code: "CZ", name: "Tschechien", postal: /^\d{3} ?\d{2}$/, example: "110 00" },
  { code: "HU", name: "Ungarn", postal: /^\d{4}$/, example: "1051" },
  { code: "CY", name: "Zypern", postal: /^\d{4}$/, example: "1010" },
] as const;

export type ShippingCountry = (typeof SHIPPING_COUNTRY_LIST)[number]["code"];

export const SHIPPING_COUNTRIES = SHIPPING_COUNTRY_LIST.map((country) => country.code) as [
  ShippingCountry,
  ...ShippingCountry[],
];

const BY_CODE = new Map<string, (typeof SHIPPING_COUNTRY_LIST)[number]>(
  SHIPPING_COUNTRY_LIST.map((country) => [country.code, country]),
);

export function shippingCountry(code: string) {
  return BY_CODE.get(code);
}

/** "1012 ab" as the backend stores it: upper case, single spaces. */
export function normalizePostalCode(value: string): string {
  return value.toUpperCase().split(/\s+/u).filter(Boolean).join(" ");
}

type RatedCountry = { code: string; name: string; rate_cents: number; free_from_cents: number | null };

/** Countries with the same terms, in their order: "Deutschland" and "the rest of the EU". */
export function shippingGroups<T extends RatedCountry>(countries: readonly T[]): T[][] {
  const groups = new Map<string, T[]>();
  for (const country of countries) {
    const key = `${country.rate_cents}/${country.free_from_cents ?? "-"}`;
    groups.set(key, [...(groups.get(key) ?? []), country]);
  }
  return [...groups.values()];
}
