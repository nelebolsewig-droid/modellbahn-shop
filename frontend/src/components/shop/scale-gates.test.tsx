import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { NavigationScaleOut } from "@/lib/api/generated/model";

import { ScaleGates } from "./scale-gates";

const SCALES: NavigationScaleOut[] = [
  { code: "Z", name: "Z", ratio: "1:220", ratio_denominator: 220, track_gauge_mm: 6.5, product_count: 0 },
  { code: "H0", name: "H0", ratio: "1:87", ratio_denominator: 87, track_gauge_mm: 16.5, product_count: 12 },
  { code: "124", name: "1:24", ratio: "1:24", ratio_denominator: 24, track_gauge_mm: null, product_count: 1 },
];

describe("ScaleGates", () => {
  it("leads into each scale with models, with ratio, track and a measured metre", () => {
    render(<ScaleGates scales={SCALES} />);
    const h0 = screen.getByRole("link", { name: "H0 · 1:87, 12 Modelle" });
    expect(h0).toHaveAttribute("href", "/katalog/h0");
    expect(h0).toHaveTextContent("Gleis 16,5 mm");
    expect(h0).toHaveTextContent("1 m ≙ 11,5 mm");
    const road = screen.getByRole("link", { name: "1:24, 1 Modell" });
    expect(road).toHaveAttribute("href", "/katalog/124");
    expect(road).toHaveTextContent("ohne Gleis");
    expect(road).toHaveTextContent("1 m ≙ 41,7 mm");
  });

  it("names the scales that have no models yet", () => {
    render(<ScaleGates scales={SCALES} />);
    expect(screen.queryByRole("link", { name: /^Z/ })).toBeNull();
    expect(screen.getByText("Noch ohne Modelle: Z · 1:220")).toBeInTheDocument();
  });
});
