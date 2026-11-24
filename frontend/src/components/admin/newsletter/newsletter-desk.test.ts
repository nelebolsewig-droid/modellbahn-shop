import { describe, expect, it } from "vitest";

import { issueDays } from "./newsletter-desk";

describe("issueDays", () => {
  it("names the days of the month in German", () => {
    expect(issueDays([1, 15])).toBe("1. und 15.");
    expect(issueDays([1, 10, 20])).toBe("1., 10. und 20.");
    expect(issueDays([1])).toBe("1.");
  });
});
