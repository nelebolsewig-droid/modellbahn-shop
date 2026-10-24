import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { StoreGalleryItemOut, StoreProductOut } from "@/lib/api/generated/model";

import { galleryFor, ProductView } from "./product-view";

function image(id: string) {
  return {
    asset_id: id,
    width: 800,
    height: 600,
    dominant_color: "#c8c8be",
    lqip: "data:image/webp;base64,AAAA",
    renditions: [{ name: "md", format: "webp" as const, width: 800, height: 600, url: `/medien/${id}/md.webp` }],
  };
}

function photo(id: string, scale: string | null, finish: string | null): StoreGalleryItemOut {
  return { image: image(id), alt_text: `Foto ${id}`, role: "gallery", scale_code: scale, finish_code: finish };
}

const PRODUCT: StoreProductOut = {
  slug: "stellwerk-altenau",
  number: 42,
  name: "Stellwerk Altenau",
  summary: "Hebelstellwerk aus dem Harz",
  description: "",
  prototype: "",
  category_path: [],
  epochs: [],
  published_at: "2026-10-24T10:00:00Z",
  finishes: [
    { code: "unpainted", name: "unbemalt", sku_letter: "U" },
    { code: "primed", name: "grundiert", sku_letter: "G" },
    { code: "painted", name: "bemalt", sku_letter: "B" },
  ],
  scales: [
    {
      code: "H0",
      name: "H0",
      ratio: "1:87",
      track_gauge_mm: 16.5,
      length_mm: 112.5,
      width_mm: null,
      height_mm: null,
      weight_g: 85,
      variants: [
        { id: "v1", finish_code: "unpainted", sku: "MB-000042-H0-U", price_cents: 3490, compare_at_price_cents: null },
        { id: "v2", finish_code: "painted", sku: "MB-000042-H0-B", price_cents: 7990, compare_at_price_cents: 8990 },
      ],
    },
    {
      code: "N",
      name: "N",
      ratio: "1:160",
      track_gauge_mm: 9,
      length_mm: null,
      width_mm: null,
      height_mm: null,
      weight_g: null,
      variants: [
        { id: "v3", finish_code: "unpainted", sku: "MB-000042-N-U", price_cents: 1990, compare_at_price_cents: null },
      ],
    },
  ],
  gallery: [photo("a", null, null), photo("b", "N", null), photo("c", "H0", "painted")],
};

describe("galleryFor", () => {
  it("puts the photos of the chosen gauge and finish first", () => {
    const order = (scale: string, finish: string) =>
      galleryFor(PRODUCT.gallery, { scale, finish }).map((item) => item.key);
    expect(order("H0", "painted")).toEqual(["c", "a", "b"]);
    expect(order("N", "unpainted")).toEqual(["b", "a", "c"]);
    expect(order("H0", "unpainted")).toEqual(["a", "c", "b"]);
  });
});

describe("ProductView", () => {
  it("shows price, SKU and dimensions of the chosen variant", async () => {
    const user = userEvent.setup();
    render(<ProductView product={PRODUCT} />);

    expect(screen.getByRole("heading", { level: 1, name: "Stellwerk Altenau" })).toBeInTheDocument();
    expect(screen.getByText("MB-000042-H0-U")).toBeInTheDocument();
    expect(screen.getByText("L 112,5 mm")).toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: "bemalt" }));
    expect(screen.getByText("MB-000042-H0-B")).toBeInTheDocument();
    expect(screen.getByText(/89,90/)).toBeInTheDocument();
  });

  it("offers only the finishes of the chosen gauge", async () => {
    const user = userEvent.setup();
    render(<ProductView product={PRODUCT} />);

    await user.click(screen.getByRole("radio", { name: /^N/ }));
    const finishes = screen.getByRole("radiogroup", { name: "Ausführung" });
    expect(within(finishes).getByRole("radio", { name: "unbemalt" })).toBeChecked();
    expect(within(finishes).getByRole("radio", { name: "bemalt (in N nicht erhältlich)" })).toBeDisabled();
    expect(screen.getByText("MB-000042-N-U")).toBeInTheDocument();
  });

  it("says why it cannot be ordered yet", () => {
    render(<ProductView product={PRODUCT} />);
    const button = screen.getByRole("button", { name: "In den Warenkorb" });
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription(/nächsten Ausbauschritt/);
  });
});
