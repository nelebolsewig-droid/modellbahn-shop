import { describe, expect, it } from "vitest";

import { partsWord, percentOf, piecesWord, topModels } from "./value";

const model = (key: string, value: number, pieces = 1) => ({ key, name: `Modell ${key}`, pieces, value_cents: value });

describe("percentOf", () => {
  it("is a share of the whole, and nothing of an empty store", () => {
    expect(percentOf(25, 100)).toBe(25);
    expect(percentOf(5, 0)).toBe(0);
    expect(percentOf(0, 10)).toBe(0);
    expect(percentOf(12, 10)).toBe(100);
  });
});

describe("topModels", () => {
  it("lists the first models with a link and folds the rest into one line", () => {
    const models = [model("a", 900), model("b", 500, 2), model("c", 300, 3), model("d", 100, 4)];
    const { rows, rest } = topModels(models, 2);
    expect(rows.map((row) => [row.key, row.href])).toEqual([
      ["a", "/admin/modelle/a"],
      ["b", "/admin/modelle/b"],
    ]);
    expect(rest).toEqual({ key: "rest", name: "2 weitere Modelle", pieces: 7, value_cents: 400 });
  });

  it("has no rest line when all fit", () => {
    expect(topModels([model("a", 1)]).rest).toBeNull();
    expect(topModels([model("a", 2), model("b", 1)], 1).rest?.name).toBe("1 weiteres Modell");
  });
});

describe("words", () => {
  it("counts pieces and parts the German way", () => {
    expect(piecesWord(1204)).toBe("1.204 Stück");
    expect([partsWord(1), partsWord(3)]).toEqual(["1 Teil", "3 Teile"]);
  });
});
