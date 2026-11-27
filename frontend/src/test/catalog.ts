import type { ProductOut, ReferencesOut, VariantOut } from "@/lib/api/generated/model";

/** The catalogue's references as the Stellwerk loads them: one scale, kit and finished model. */
export const REFERENCES: ReferencesOut = {
  scales: [{ code: "H0", name: "H0", ratio: "1:87", ratio_denominator: 87, track_gauge_mm: 16.5 }],
  finishes: [
    { code: "unpainted", name: "Bausatz", sku_letter: "B", colored: false, offered: true },
    { code: "painted", name: "Fertigmodell", sku_letter: "F", colored: true, offered: true },
  ],
  epochs: [],
};

export function variantOut(overrides: Partial<VariantOut> = {}): VariantOut {
  return {
    id: "v1",
    finish_code: "unpainted",
    color: "",
    sku: "MB-000001-H0-B",
    gtin: "2000000000015",
    price_cents: 4990,
    compare_at_price_cents: null,
    active: true,
    allow_backorder: false,
    lead_time_min_weeks: null,
    lead_time_max_weeks: null,
    ...overrides,
  };
}

/** A model in H0 with the given Ausführungen (a kit by default). */
export function productOut(overrides: Partial<ProductOut> = {}, variants: VariantOut[] = [variantOut()]): ProductOut {
  return {
    id: "p1",
    number: 1,
    name: "Stellwerk Altenau",
    slug: "stellwerk-altenau",
    status: "draft",
    summary: "",
    description: "",
    prototype: "",
    label: "adp",
    primary_category_id: null,
    epoch_codes: [],
    scales: [{ id: "s1", scale_code: "H0", length_mm: null, width_mm: null, height_mm: null, weight_g: null, variants }],
    media: [],
    publish_blockers: [],
    published_at: null,
    archived_at: null,
    created_at: "2026-11-15T10:00:00Z",
    updated_at: "2026-11-15T10:00:00Z",
    version: 1,
    ...overrides,
  };
}
