/*
 * The codes on the workshop's labels, read the same way as by the backend
 * (backend/src/modellbahn/modules/inventory/domain/codes.py and scanning.py):
 *
 * - Unit: ten characters of Crockford's Base32 with a Luhn mod 32 check character,
 *   on the label as Code 128 and in groups of four (7KQ2 X9F4 MZ).
 * - Location: segments joined by hyphens (R02-F04-B12), as Code 128.
 * - Variant: the EAN-13 the till (SumUp) knows the article by.
 * - Part: the part number (STW-ALT-DACH-H0) on the label of a box of printed parts,
 *   as Code 128. It looks like a location code too, so it comes after the locations.
 *
 * The scanner uses this to tell at once what was scanned and to refuse garbage without
 * asking the server; the server decides what exists.
 */

export const ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";
const UNIT_CODE = /^[0-9A-HJKMNP-TV-Z]{10}$/;
const LOCATION_CODE = /^[A-Z0-9]{1,8}(?:-[A-Z0-9]{1,8}){0,4}$/;
const EAN13 = /^[0-9]{13}$/;
const PART_NUMBER = /^[A-Z0-9]+(?:-[A-Z0-9]+)*$/;
const PART_NUMBER_MAX_LENGTH = 40;
const MAX_RAW_LENGTH = 300;
const READ_AS: Readonly<Record<string, string>> = { O: "0", I: "1", L: "1" };

export type CodeKind = "unit" | "location" | "variant" | "part";
export type Reading = { kind: CodeKind; code: string };

function luhnSum(code: string, startFactor: 1 | 2): number {
  let factor: number = startFactor;
  let total = 0;
  for (const char of [...code].reverse()) {
    const addend = factor * ALPHABET.indexOf(char);
    factor = 3 - factor;
    total += Math.floor(addend / 32) + (addend % 32);
  }
  return total;
}

/** The check character for nine characters of the alphabet. */
export function checkCharacter(body: string): string {
  const remainder = luhnSum(body, 2) % 32;
  return ALPHABET.charAt((32 - remainder) % 32);
}

export function isValidUnitCode(code: string): boolean {
  return UNIT_CODE.test(code) && luhnSum(code, 1) % 32 === 0;
}

/** Upper case, without spaces and hyphens, with O read as 0 and I or L as 1. */
export function normalizeUnitCode(text: string): string {
  return text
    .replace(/[\s-]+/g, "")
    .toUpperCase()
    .replace(/[OIL]/g, (char) => READ_AS[char] ?? char);
}

/** `7KQ2X9F4MZ` as people read it aloud: `7KQ2 X9F4 MZ`. */
export function formatUnitCode(code: string): string {
  return `${code.slice(0, 4)} ${code.slice(4, 8)} ${code.slice(8)}`;
}

export function isValidEan13(digits: string): boolean {
  if (!EAN13.test(digits)) {
    return false;
  }
  const total = [...digits.slice(0, 12)].reduce(
    (sum, digit, index) => sum + Number(digit) * (index % 2 ? 3 : 1),
    0,
  );
  return (10 - (total % 10)) % 10 === Number(digits[12]);
}

function fromUrl(text: string): Reading[] | null {
  if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(text) && !text.startsWith("/")) {
    return null;
  }
  let path: string;
  try {
    path = new URL(text, "https://scan.invalid").pathname;
  } catch {
    return [];
  }
  const segments = path.split("/").filter(Boolean);
  if (segments.length < 2) {
    return [];
  }
  const [marker = "", code = ""] = segments.slice(-2);
  if (marker === "u") {
    const unit = normalizeUnitCode(code);
    return isValidUnitCode(unit) ? [{ kind: "unit", code: unit }] : [];
  }
  if (marker === "l") {
    const location = code.toUpperCase();
    return LOCATION_CODE.test(location) ? [{ kind: "location", code: location }] : [];
  }
  return [];
}

/** The readings of a scan worth asking the server about, most likely first. */
export function interpretations(raw: string): Reading[] {
  const text = raw.trim();
  if (text === "" || text.length > MAX_RAW_LENGTH) {
    return [];
  }
  const url = fromUrl(text);
  if (url !== null) {
    return url;
  }
  if (isValidEan13(text)) {
    return [{ kind: "variant", code: text }];
  }
  const readings: Reading[] = [];
  const unit = normalizeUnitCode(text);
  if (isValidUnitCode(unit)) {
    readings.push({ kind: "unit", code: unit });
  }
  const location = text.toUpperCase();
  if (LOCATION_CODE.test(location)) {
    const groups = location.split("-").map((part) => part.length);
    const groupedLikeUnit = groups.join() === "4,4,2";
    const reading: Reading = { kind: "location", code: location };
    if (location.includes("-") && !groupedLikeUnit) {
      readings.unshift(reading);
    } else {
      readings.push(reading);
    }
  }
  if (location.length <= PART_NUMBER_MAX_LENGTH && PART_NUMBER.test(location)) {
    readings.push({ kind: "part", code: location });
  }
  return readings;
}
