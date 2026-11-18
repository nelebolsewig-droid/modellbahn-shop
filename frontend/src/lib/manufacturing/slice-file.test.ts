import { describe, expect, it } from "vitest";

import {
  plateValues,
  printDuration,
  SLICE_HEAD_BYTES,
  sliceHead,
} from "./slice-file";

const PLATE = {
  format: "ctb",
  machine: "ELEGOO Saturn 4 Ultra 16K",
  volume_ml: 62.287,
  grams: 68.516,
  cost: 2.055,
  print_seconds: 9866,
  layer_height_um: 50,
  layer_count: 1409,
};

describe("sliceHead", () => {
  it("sends only the head of a big file", async () => {
    const file = new Blob([new Uint8Array(SLICE_HEAD_BYTES + 1000).fill(0xab)]);
    const head = atob(await sliceHead(file));
    expect(head).toHaveLength(SLICE_HEAD_BYTES);
    expect(head.charCodeAt(0)).toBe(0xab);
  });
});

describe("plateValues", () => {
  it("divides the plate's resin by the parts on it", () => {
    expect(plateValues(PLATE, 4)).toEqual({
      plate_minutes: "164",
      layer_height_um: "50",
      material_per_part: "15,57",
    });
  });

  it("takes the whole plate as one part when the number is missing", () => {
    expect(plateValues(PLATE, Number.NaN).material_per_part).toBe("62,29");
  });
});

it("writes a print time as hours and minutes", () => {
  expect(printDuration(9866)).toBe("2 h 44 min");
  expect(printDuration(1500)).toBe("25 min");
});
