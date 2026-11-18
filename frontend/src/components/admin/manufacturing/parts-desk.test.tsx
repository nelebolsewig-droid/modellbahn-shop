import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { MaterialOut } from "@/lib/api/generated/model";
import { requestsTo, routeFetch } from "@/test/fetch-routes";
import { jsonResponse, renderWithQueryClient } from "@/test/render";

import { PartsDesk } from "./parts-desk";

const fetchMock = vi.fn<typeof fetch>();
const BASE = "/api/v1/admin/manufacturing";

const RESIN: MaterialOut = {
  id: "m1",
  name: "Resin grau",
  technology: "resin",
  notes: "",
  active: true,
  price_cents: null,
  part_count: 3,
};

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
});

describe("Material", () => {
  it("asks for the price of a litre and keeps it when the material is archived", async () => {
    let material = RESIN;
    routeFetch(fetchMock, {
      [`GET ${BASE}/materials`]: () => jsonResponse({ items: [material] }),
      [`GET ${BASE}/parts`]: () => jsonResponse({ items: [] }),
      [`GET /api/v1/admin/catalog/references`]: () => jsonResponse({ scales: [], finishes: [], categories: [], epochs: [] }),
      [`PUT ${BASE}/materials/m1`]: (request) => {
        material = { ...material, ...(request.body as Partial<MaterialOut>) };
        return jsonResponse(material);
      },
    });
    const user = userEvent.setup();
    renderWithQueryClient(<PartsDesk staffRole="owner" />);

    const row = (await screen.findByText("Resin grau")).closest("li") as HTMLElement;
    expect(row).toHaveTextContent("kein Preis");
    await user.click(within(row).getByRole("button", { name: "Preis" }));
    const dialog = await screen.findByRole("dialog", { name: "Preis von Resin grau" });
    await user.type(within(dialog).getByLabelText("Preis je Liter in Euro"), "39,90");
    await user.click(within(dialog).getByRole("button", { name: "Preis speichern" }));

    await waitFor(() => expect(requestsTo(fetchMock, `PUT ${BASE}/materials/m1`)).toHaveLength(1));
    expect(requestsTo(fetchMock, `PUT ${BASE}/materials/m1`)[0]?.body).toEqual({
      name: "Resin grau",
      notes: "",
      active: true,
      price_cents: 3990,
    });
    await waitFor(() => expect(row).toHaveTextContent("je Liter"));

    // Archiving sends no price, so the server keeps it.
    await user.click(within(row).getByRole("button", { name: "Archivieren" }));
    await waitFor(() => expect(requestsTo(fetchMock, `PUT ${BASE}/materials/m1`)).toHaveLength(2));
    expect(requestsTo(fetchMock, `PUT ${BASE}/materials/m1`)[1]?.body).not.toHaveProperty("price_cents");
  });
});
