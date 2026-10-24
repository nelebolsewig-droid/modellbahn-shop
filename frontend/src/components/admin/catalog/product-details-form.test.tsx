import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ProductOut } from "@/lib/api/generated/model";
import { jsonResponse, problemResponse, renderWithQueryClient } from "@/test/render";

import { ProductDetailsForm } from "./product-details-form";

const PRODUCT: ProductOut = {
  id: "p1",
  number: 1,
  slug: "stellwerk-altenau",
  name: "Stellwerk Altenau",
  summary: "",
  description: "",
  prototype: "",
  primary_category_id: null,
  status: "draft",
  published_at: null,
  archived_at: null,
  created_at: "2026-10-24T10:00:00Z",
  updated_at: "2026-10-24T10:00:00Z",
  version: 1,
  epoch_codes: [],
  scales: [],
  media: [],
  publish_blockers: ["no_category", "no_active_variant", "no_main_image"],
};

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
});

function renderForm(product: ProductOut = PRODUCT) {
  return renderWithQueryClient(
    <ProductDetailsForm
      product={product}
      categories={[
        { id: "c1", parent_id: null, slug: "gebaeude", name: "Gebäude", position: 0 },
        { id: "c2", parent_id: "c1", slug: "stellwerke", name: "Stellwerke", position: 0 },
      ]}
      epochs={[{ code: "III", name: "Epoche III", period: "1949-1970" }]}
    />,
  );
}

describe("ProductDetailsForm", () => {
  it("sends only the changed fields, with the version as If-Match", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ ...PRODUCT, prototype: "Altenau (Harz)", primary_category_id: "c2", epoch_codes: ["III"], version: 2 }),
    );
    renderForm();

    await user.type(screen.getByLabelText("Vorbild"), "Altenau (Harz)");
    await user.selectOptions(screen.getByLabelText("Kategorie"), "c2");
    await user.click(screen.getByRole("checkbox", { name: /III/ }));
    await user.click(screen.getByRole("button", { name: "Stammdaten speichern" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/v1/admin/products/p1");
    expect(new Headers(init?.headers).get("If-Match")).toBe('"1"');
    expect(JSON.parse(String(init?.body))).toEqual({
      prototype: "Altenau (Harz)",
      primary_category_id: "c2",
      epoch_codes: ["III"],
    });
    expect(await screen.findByRole("button", { name: "Stammdaten speichern" })).toBeDisabled();
  });

  it("shows a taken address at the field", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(problemResponse(409, "slug_taken"));
    renderForm();

    const slug = screen.getByLabelText("Adresse im Shop");
    await user.clear(slug);
    await user.type(slug, "lokschuppen");
    await user.click(screen.getByRole("button", { name: "Stammdaten speichern" }));

    expect(await screen.findByText(/Adresse ist schon vergeben/)).toBeInTheDocument();
  });

  it("keeps the address of a published product fixed", () => {
    renderForm({ ...PRODUCT, status: "active", published_at: "2026-10-24T10:00:00Z" });
    expect(screen.getByLabelText("Adresse im Shop")).toHaveAttribute("readonly");
  });
});
