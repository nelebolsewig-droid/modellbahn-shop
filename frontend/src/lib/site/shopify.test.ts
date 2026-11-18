import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiProblem } from "@/lib/api/problem";
import { fetchStore } from "@/lib/api/server";

import { collectionTarget, legacyRedirect, productTarget, searchTarget, searchWords } from "./shopify";

vi.mock("@/lib/api/server", () => ({ fetchStore: vi.fn() }));
vi.mock("./shopify-produkte.json", () => ({ default: { "edk-6-kran-h0": "eisenbahndrehkran-edk-6" } }));

const fetchStoreMock = vi.mocked(fetchStore);

describe("productTarget", () => {
  beforeEach(() => {
    fetchStoreMock.mockReset();
  });

  it("follows a handle that the export renamed, without asking the API", async () => {
    await expect(productTarget("EDK-6-Kran-H0")).resolves.toEqual({
      path: "/produkte/eisenbahndrehkran-edk-6",
      permanent: true,
    });
    expect(fetchStoreMock).not.toHaveBeenCalled();
  });

  it("keeps a handle that is a product here", async () => {
    fetchStoreMock.mockResolvedValue({ slug: "kipper-3-achser" });
    await expect(productTarget("kipper-3-achser")).resolves.toEqual({
      path: "/produkte/kipper-3-achser",
      permanent: true,
    });
    expect(fetchStoreMock).toHaveBeenCalledWith("/products/kipper-3-achser");
  });

  it("searches the catalogue for an unknown handle, only for now", async () => {
    fetchStoreMock.mockResolvedValue(null);
    await expect(productTarget("magirus-dl-30-feuerwehr")).resolves.toEqual({
      path: "/katalog?suche=magirus+dl+30+feuerwehr",
      permanent: false,
    });
  });

  it("searches as well while the API is down", async () => {
    fetchStoreMock.mockRejectedValue(ApiProblem.network(new Error("offline")));
    await expect(productTarget("kipper")).resolves.toEqual({ path: "/katalog?suche=kipper", permanent: false });
  });

  it("does not ask the API for something that is no handle", async () => {
    await expect(productTarget("../admin")).resolves.toEqual({ path: "/katalog?suche=admin", permanent: false });
    expect(fetchStoreMock).not.toHaveBeenCalled();
  });
});

describe("collectionTarget", () => {
  it("sends a collection to its category, which the catalogue resolves", () => {
    expect(collectionTarget("lkw")).toEqual({ path: "/katalog?kategorie=lkw", permanent: true });
  });

  it("sends the whole range to the catalogue", () => {
    expect(collectionTarget("all")).toEqual({ path: "/katalog", permanent: true });
    expect(collectionTarget("frontpage")).toEqual({ path: "/katalog", permanent: true });
  });
});

describe("searchTarget", () => {
  it("carries the words over", () => {
    expect(searchTarget(" Kran ")).toEqual({ path: "/katalog?suche=Kran", permanent: true });
    expect(searchTarget(null)).toEqual({ path: "/katalog", permanent: true });
  });
});

describe("searchWords", () => {
  it("turns hyphens into spaces", () => {
    expect(searchWords("lkw-mit-plane_h0")).toBe("lkw mit plane h0");
  });
});

describe("legacyRedirect", () => {
  it("answers 301 with a relative address for a certain target", () => {
    const response = legacyRedirect({ path: "/agb", permanent: true });
    expect(response.status).toBe(301);
    expect(response.headers.get("Location")).toBe("/agb");
  });

  it("answers 302, not cached, for a guess", () => {
    const response = legacyRedirect({ path: "/katalog?suche=x", permanent: false });
    expect(response.status).toBe(302);
    expect(response.headers.get("Cache-Control")).toBe("no-store");
  });
});
