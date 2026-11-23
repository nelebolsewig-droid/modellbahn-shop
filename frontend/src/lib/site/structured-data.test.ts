import { describe, expect, it, vi } from "vitest";

import type { StoreProductOut, VariantAvailabilityOut } from "@/lib/api/generated/model";

import { breadcrumbJsonLd, feedItems, feedXml, productJsonLd, serializeJsonLd, storeJsonLd } from "./structured-data";

vi.mock("@/lib/api/server", () => ({ fetchStore: vi.fn() }));

const BASE = "https://www.adp-modelle.de";

const PRODUCT: StoreProductOut = {
  category_path: [{ name: "Kräne", slug: "kraene" }],
  description: "Lang.",
  epochs: [],
  finishes: [{ code: "fm", name: "Fertigmodell", colored: true, offered: true, sku_letter: "F" }],
  gallery: [
    {
      alt_text: "EDK 6",
      color: null,
      finish_code: null,
      role: "gallery" as StoreProductOut["gallery"][number]["role"],
      scale_code: null,
      image: {
        asset_id: "a",
        dominant_color: "#fff",
        height: 600,
        width: 800,
        lqip: "",
        renditions: [{ name: "lg", format: "webp", width: 1600, height: 1200, url: "/medien/a/lg.webp" }],
      },
    },
  ],
  name: "EDK 6 <Kran>",
  number: 12,
  prototype: "",
  published_at: null,
  scales: [
    {
      code: "H0",
      name: "H0",
      ratio: "1:87",
      height_mm: null,
      length_mm: null,
      width_mm: null,
      weight_g: null,
      track_gauge_mm: 16.5,
      variants: [
        { id: "v1", sku: "12-H0-F-rot", finish_code: "fm", color: "rot", price_cents: 4990, compare_at_price_cents: 5990 },
        { id: "v2", sku: "12-H0-F-gelb", finish_code: "fm", color: "gelb", price_cents: 4990, compare_at_price_cents: null },
      ],
    },
  ],
  slug: "edk-6",
  summary: "Eisenbahndrehkran.",
};

const AVAILABILITY: VariantAvailabilityOut[] = [
  { variant_id: "v1", availability: "in_stock", free_units: 2, lead_time_min_weeks: 3, lead_time_max_weeks: 5 },
  { variant_id: "v2", availability: "made_to_order", free_units: 0, lead_time_min_weeks: 3, lead_time_max_weeks: 5 },
];

describe("productJsonLd", () => {
  it("has one offer per variant with absolute image, price and availability", () => {
    const data = productJsonLd(PRODUCT, AVAILABILITY, BASE, "adp-Modelle") as { image: string[]; offers: { availability: string }[] };
    expect(data.image).toEqual([`${BASE}/medien/a/lg.webp`]);
    expect(data.offers).toHaveLength(2);
    expect(data.offers[0]).toMatchObject({ price: "49.90", priceCurrency: "EUR", availability: "https://schema.org/InStock" });
    expect(data.offers[1]?.availability).toBe("https://schema.org/MadeToOrder");
  });
});

describe("breadcrumbJsonLd", () => {
  it("leads from the catalogue to the product", () => {
    const data = breadcrumbJsonLd(PRODUCT, BASE) as { itemListElement: { name: string; item: string }[] };
    expect(data.itemListElement.map((c) => c.name)).toEqual(["Modelle", "H0 · 1:87", "Kräne", "EDK 6 <Kran>"]);
    expect(data.itemListElement.at(-1)?.item).toBe(`${BASE}/produkte/edk-6`);
  });
});

describe("serializeJsonLd", () => {
  it("cannot close the script tag", () => {
    expect(serializeJsonLd({ name: "</script>" })).not.toContain("</script>");
  });
});

describe("storeJsonLd", () => {
  it("works without imprint", () => {
    expect(storeJsonLd(null, BASE, "adp-Modelle")).toMatchObject({ "@type": "OnlineStore", url: `${BASE}/` });
  });
});

describe("feed", () => {
  it("lists variants, sale price and handling time for made to order", () => {
    const items = feedItems(PRODUCT, AVAILABILITY, BASE);
    expect(items[0]).toMatchObject({ id: "12-H0-F-rot", price: "59.90 EUR", salePrice: "49.90 EUR", availability: "in_stock", minHandlingDays: null });
    expect(items[1]).toMatchObject({ availability: "in_stock", minHandlingDays: 15, maxHandlingDays: 25 });
    const xml = feedXml(items, BASE, "adp-Modelle", "adp-Modelle");
    expect(xml).toContain("<g:title>EDK 6 &lt;Kran&gt; (H0 · 1:87, Fertigmodell, rot)</g:title>");
    expect(xml).toContain("<g:max_handling_time>25</g:max_handling_time>");
  });

  it("leaves out products without a picture", () => {
    expect(feedItems({ ...PRODUCT, gallery: [] }, AVAILABILITY, BASE)).toEqual([]);
  });
});
