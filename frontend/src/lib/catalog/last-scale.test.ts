import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { rememberScale, useCatalogHref, useLastScale } from "@/lib/catalog/last-scale";

describe("last scale", () => {
  afterEach(() => window.localStorage.clear());

  it("leads to the choice of scales until one was browsed", () => {
    const { result } = renderHook(() => useCatalogHref());
    expect(result.current).toBe("/katalog");
  });

  it("leads straight to the scale browsed last", () => {
    const { result } = renderHook(() => ({
      href: useCatalogHref(),
      last: useLastScale(),
    }));
    act(() => rememberScale({ code: "H0", name: "H0" }));
    expect(result.current.href).toBe("/katalog/h0");
    expect(result.current.last).toEqual({ code: "H0", name: "H0" });
  });

  it("ignores what it cannot read", () => {
    window.localStorage.setItem("adp.massstab", "{kaputt");
    const { result } = renderHook(() => useLastScale());
    expect(result.current).toBeNull();
  });
});
