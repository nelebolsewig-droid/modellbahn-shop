import { describe, expect, it } from "vitest";

import type { LocationKind, LocationNodeOut } from "@/lib/api/generated/model";

import { childCode, childKinds, labelCodes, subtree } from "./locations";

function node(code: string, path: string, kind: LocationKind): LocationNodeOut {
  return {
    id: code,
    code,
    path,
    kind,
    name: "",
    depth: path.split(".").length - 1,
    parent_id: null,
    holds_goods: kind === "compartment" || kind === "box" || kind === "staging",
    unit_count: 0,
    total_count: 0,
    part_count: 0,
  };
}

const TREE = [
  node("LAGER", "LAGER", "site"),
  node("R01", "LAGER.R01", "shelf"),
  node("R01-F01", "LAGER.R01.F01", "compartment"),
  node("R01-F01-B1", "LAGER.R01.F01.B1", "box"),
  node("R010", "LAGER.R010", "shelf"),
  node("PACK", "LAGER.PACK", "staging"),
];

describe("locations", () => {
  it("builds the code like the backend: the site stays out", () => {
    expect(childCode(null, " lager ")).toBe("LAGER");
    expect(childCode({ kind: "site", code: "LAGER" }, "r02")).toBe("R02");
    expect(childCode({ kind: "shelf", code: "R02" }, "F04")).toBe("R02-F04");
  });

  it("offers the kinds the backend allows below a parent", () => {
    expect(childKinds(null)).toEqual(["site"]);
    expect(childKinds({ kind: "shelf", code: "R01" })).toEqual(["compartment", "box"]);
    expect(childKinds({ kind: "box", code: "R01-B1" })).toEqual([]);
  });

  it("finds a location and what lies below it, not a sibling with the same prefix", () => {
    expect(subtree(TREE, "R01").map((item) => item.code)).toEqual(["R01", "R01-F01", "R01-F01-B1"]);
    expect(subtree(TREE, "NOPE")).toEqual([]);
  });

  it("labels everything but the site", () => {
    expect(labelCodes(TREE)).toEqual(["R01", "R01-F01", "R01-F01-B1", "R010", "PACK"]);
  });
});
