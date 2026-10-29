import { describe, expect, it } from "vitest";

import { balloonOpacity, explosionAt, formatDuration, hoursOf, partShare, phaseAt, totalsOf } from "./explosion";
import { PLACEHOLDER_MODEL } from "./placeholder-model";

describe("the parts list", () => {
  it("adds up parts, print time and handwork", () => {
    expect(totalsOf(PLACEHOLDER_MODEL)).toEqual({ parts: 23, printMinutes: 1600, handworkMinutes: 360 });
    expect(hoursOf(1600)).toBe(27);
  });

  it("numbers the positions without gaps", () => {
    expect(PLACEHOLDER_MODEL.parts.map((part) => part.position)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]);
  });

  it.each([
    [160, "2 h 40"],
    [240, "4 h"],
    [50, "50 min"],
    [65, "1 h 05"],
  ])("writes %i minutes as %s", (minutes, text) => {
    expect(formatDuration(minutes)).toBe(text);
  });
});

describe("scrolling through the drawing", () => {
  it("takes the model apart, holds, and puts it back together", () => {
    expect(explosionAt(0)).toBe(0);
    expect(explosionAt(0.25)).toBeGreaterThan(0);
    expect(explosionAt(0.25)).toBeLessThan(1);
    expect(explosionAt(0.55)).toBe(1);
    expect(explosionAt(0.82)).toBeLessThan(1);
    expect(explosionAt(1)).toBe(0);
  });

  it("follows the process: take apart, print, put together", () => {
    expect([0, 0.3, 0.5, 0.65, 0.8, 1].map(phaseAt)).toEqual([0, 0, 1, 1, 2, 2]);
  });

  it("moves the parts that come off first ahead of the others", () => {
    const first = partShare(0.3, 0, 10);
    const last = partShare(0.3, 10, 10);
    expect(first).toBeGreaterThan(last);
    expect(partShare(0, 0, 10)).toBe(0);
    expect(partShare(1, 10, 10)).toBe(1);
  });

  it("shows the balloons only once the parts are apart", () => {
    expect(balloonOpacity(0.3)).toBe(0);
    expect(balloonOpacity(1)).toBe(1);
  });
});
