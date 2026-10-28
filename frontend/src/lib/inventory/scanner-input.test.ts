import { describe, expect, it, vi } from "vitest";

import { ARTICLE_HOLD_MS, LabelPicker, RepeatFilter, WedgeReader } from "./scanner-input";

function type(reader: WedgeReader, text: string, start: number, gap: number): number {
  let time = start;
  for (const key of [...text, "Enter"]) {
    reader.feed(key, time);
    time += gap;
  }
  return time;
}

describe("WedgeReader", () => {
  it("reports a fast burst ending in Enter as a scan", () => {
    const onScan = vi.fn();
    const reader = new WedgeReader(onScan);
    type(reader, "7KQ2X9F4MZ", 1000, 8);
    expect(onScan).toHaveBeenCalledExactlyOnceWith("7KQ2X9F4MZ");
  });

  it("ignores people typing and short bursts", () => {
    const onScan = vi.fn();
    const reader = new WedgeReader(onScan);
    type(reader, "R01-F01", 1000, 120);
    type(reader, "R01", 5000, 5);
    expect(onScan).not.toHaveBeenCalled();
  });

  it("starts over after a pause and ignores keys like Shift", () => {
    const onScan = vi.fn();
    const reader = new WedgeReader(onScan);
    reader.feed("x", 0);
    reader.feed("Shift", 500);
    expect(reader.feed("Enter", 501)).toBe(false);
    type(reader, "2000000000015", 1000, 10);
    expect(onScan).toHaveBeenCalledExactlyOnceWith("2000000000015");
  });

  it("tells the caller which Enter finished a scan", () => {
    const reader = new WedgeReader(() => undefined);
    for (const [index, key] of [..."ABCDEFG"].entries()) {
      expect(reader.feed(key, index * 5)).toBe(false);
    }
    expect(reader.feed("Enter", 40)).toBe(true);
  });
});

describe("RepeatFilter", () => {
  it("lets a code through once per window", () => {
    const filter = new RepeatFilter(1500);
    expect(filter.accept("A", 0)).toBe(true);
    expect(filter.accept("A", 400)).toBe(false);
    expect(filter.accept("B", 500)).toBe(true);
    expect(filter.accept("A", 2000)).toBe(true);
  });
});

describe("LabelPicker", () => {
  const ARTICLE = "2000000000008";
  const UNIT = "J4WZXRT2S2";

  it("takes the unit's own code when the article's EAN is in the picture too", () => {
    const onPick = vi.fn();
    const picker = new LabelPicker(onPick);
    picker.frame([ARTICLE], 0);
    picker.frame([ARTICLE, UNIT], 100);
    picker.frame([ARTICLE], 600);
    picker.frame([], 1200);
    expect(onPick.mock.calls).toEqual([[UNIT]]);
  });

  it("takes an EAN that stays alone for a moment", () => {
    const onPick = vi.fn();
    const picker = new LabelPicker(onPick);
    picker.frame([ARTICLE], 0);
    picker.frame([ARTICLE], ARTICLE_HOLD_MS - 1);
    expect(onPick).not.toHaveBeenCalled();
    picker.frame([], ARTICLE_HOLD_MS);
    expect(onPick).toHaveBeenCalledExactlyOnceWith(ARTICLE);
  });

  it("reads a location label at once", () => {
    const onPick = vi.fn();
    new LabelPicker(onPick).frame(["R01-F02"], 0);
    expect(onPick).toHaveBeenCalledExactlyOnceWith("R01-F02");
  });
});
