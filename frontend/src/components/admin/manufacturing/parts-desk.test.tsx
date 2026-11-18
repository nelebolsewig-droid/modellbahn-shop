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

describe("Druckdatei", () => {
  const PLATE = {
    format: "ctb",
    machine: "ELEGOO Saturn 4 Ultra 16K",
    volume_ml: 62.287,
    grams: 68.516,
    cost: 2.055,
    print_seconds: 9866,
    layer_height_um: 50,
    layer_count: 1409,
  };

  function routes(read: () => Response) {
    routeFetch(fetchMock, {
      [`GET ${BASE}/materials`]: () => jsonResponse({ items: [RESIN] }),
      [`GET ${BASE}/parts`]: () => jsonResponse({ items: [] }),
      [`GET /api/v1/admin/catalog/references`]: () =>
        jsonResponse({ scales: [{ code: "TT", name: "TT" }], finishes: [], categories: [], epochs: [] }),
      [`POST ${BASE}/slice-files/read`]: read,
    });
  }

  it("fills plate time, layer and the resin of one part from the sliced file", async () => {
    routes(() => jsonResponse(PLATE));
    const user = userEvent.setup();
    renderWithQueryClient(<PartsDesk staffRole="owner" />);

    await user.click(await screen.findByRole("button", { name: /Neues Teil/ }));
    const dialog = await screen.findByRole("dialog", { name: "Neues Teil" });
    const perPlate = within(dialog).getByLabelText("Teile je Platte");
    await user.clear(perPlate);
    await user.type(perPlate, "4");
    const file = new File([new Uint8Array([7, 1, 0xfd, 0x12, 0, 0])], "drehgestell.ctb");
    await user.upload(within(dialog).getByLabelText("Druckdatei wählen"), file);

    await waitFor(() => expect(within(dialog).getByLabelText("Material je Teil (ml)")).toHaveValue("15,57"));
    expect(within(dialog).getByLabelText("Volle Platte (min)")).toHaveValue("164");
    expect(within(dialog).getByLabelText("Schicht (µm)")).toHaveValue("50");
    expect(dialog).toHaveTextContent("ELEGOO Saturn 4 Ultra 16K");
    expect(dialog).toHaveTextContent("geteilt durch 4 Teile je Platte");
    expect(requestsTo(fetchMock, `POST ${BASE}/slice-files/read`)[0]?.body).toEqual({ head: "BwH9EgAA" });
  });

  it("says when the file is no sliced plate", async () => {
    routes(() =>
      jsonResponse(
        {
          type: "/problems/validation-failed",
          title: "Unprocessable",
          status: 422,
          detail: "Invalid input.",
          code: "validation_failed",
          errors: [{ field: "head", code: "slice_file_unreadable", message: "x" }],
        },
        422,
        "application/problem+json",
      ),
    );
    const user = userEvent.setup();
    renderWithQueryClient(<PartsDesk staffRole="owner" />);

    await user.click(await screen.findByRole("button", { name: /Neues Teil/ }));
    const dialog = await screen.findByRole("dialog", { name: "Neues Teil" });
    await user.upload(within(dialog).getByLabelText("Druckdatei wählen"), new File(["solid"], "teil.ctb"));

    await waitFor(() => expect(dialog).toHaveTextContent("nicht die .chitubox- oder STL-Datei"));
  });
});
