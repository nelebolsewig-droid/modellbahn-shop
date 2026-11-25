import { describe, expect, it } from "vitest";

import { finishFor, labelFor, labelName } from "./filters";
import { catalogPath } from "./scales";

describe("shop filters", () => {
  it("maps the German words to the API's codes", () => {
    expect(finishFor("bausatz")).toBe("unpainted");
    expect(finishFor("fertigmodell")).toBe("painted");
    expect(finishFor("lackiert")).toBeUndefined();
    expect(labelFor("milmod")).toBe("milmod");
    expect(labelFor("andere")).toBeUndefined();
    expect(labelName("vehicle-world")).toBe("Vehicle World");
  });

  it("keeps them in the list's address", () => {
    expect(catalogPath({ scale: "H0", ausfuehrung: "bausatz", label: "adp", epoche: "III" })).toBe(
      "/katalog/h0?ausfuehrung=bausatz&label=adp&epoche=III",
    );
  });
});
