import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { LocationNodeOut, QuickEntryIn, VariantOut } from "@/lib/api/generated/model";
import { productOut, REFERENCES, variantOut } from "@/test/catalog";
import { requestsTo, routeFetch } from "@/test/fetch-routes";
import { jsonResponse, problemResponse, renderWithQueryClient } from "@/test/render";

import { ModelWizard, plannedVariants } from "./model-wizard";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const fetchMock = vi.fn<typeof fetch>();
const QUICK = "POST /api/v1/admin/catalog/quick-entries";
const UNITS = "POST /api/v1/admin/inventory/units";
const PUBLISH = "POST /api/v1/admin/products/p1/publish";

const BODEN: LocationNodeOut = {
  id: "l1",
  code: "R01-B01",
  path: "LAGER.R01.B01",
  kind: "compartment",
  name: "Boden 1",
  parent_id: "l0",
  holds_goods: true,
  depth: 2,
  unit_count: 0,
  total_count: 0,
  part_count: 0,
  place: "Regal 1, Boden 1",
};

/** The catalogue and the store; ``failOnce`` makes the n-th call (from 1) of a route fail once. */
function desk(failOnce: { quick?: number; units?: number } = {}) {
  const made: VariantOut[] = [];
  const calls = { quick: 0, units: 0 };
  const failing = (route: "quick" | "units") => {
    calls[route] += 1;
    if (calls[route] === failOnce[route]) {
      delete failOnce[route];
      return true;
    }
    return false;
  };
  routeFetch(fetchMock, {
    "GET /api/v1/admin/catalog/references": () => jsonResponse(REFERENCES),
    "GET /api/v1/admin/categories": () => jsonResponse([]),
    "GET /api/v1/admin/inventory/locations": () => jsonResponse({ items: [BODEN] }),
    [QUICK]: ({ body }) => {
      if (failing("quick")) {
        return problemResponse(503, "service_unavailable");
      }
      const entry = body as QuickEntryIn;
      const variant = variantOut({
        id: `v${made.length + 1}`,
        finish_code: entry.finish_code,
        color: entry.color ?? "",
        sku: `MB-000001-H0-${made.length + 1}`,
        price_cents: entry.price_cents,
      });
      made.push(variant);
      return jsonResponse({ product: productOut({}, [...made]), variant, new_product: made.length === 1, new_variant: true }, 201);
    },
    [UNITS]: ({ body }) => {
      if (failing("units")) {
        return problemResponse(503, "service_unavailable");
      }
      const { quantity } = body as { quantity: number };
      return jsonResponse({ items: Array.from({ length: quantity }, (_, index) => ({ id: `u${index}` })) }, 201);
    },
    [PUBLISH]: () => jsonResponse(productOut({ status: "active" })),
  });
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  window.localStorage.clear();
  push.mockReset();
});

afterEach(() => {
  fetchMock.mockReset();
});

describe("Neues Modell", () => {
  it("goes from name to Ausführungen, stock, labels and the shop, and ends on the model", async () => {
    desk();
    const user = userEvent.setup();
    renderWithQueryClient(<ModelWizard />);

    // 1 · Name und Fotos
    await user.type(await screen.findByLabelText("Name"), "IFA W50 Kipper");
    await user.click(screen.getByRole("button", { name: "Weiter" }));

    // 2 · Maßstab, Ausführungen, Farben, Preis
    expect(screen.getByRole("heading", { name: /Ausführungen und Preis/ })).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: /H0/ }));
    await user.click(screen.getByRole("checkbox", { name: "Bausatz" }));
    await user.type(screen.getByLabelText("Preis Bausatz"), "25");
    await user.click(screen.getByRole("checkbox", { name: "Fertigmodell" }));
    await user.type(screen.getByLabelText("Preis Fertigmodell"), "49,90");
    for (const color of ["Rot", "blau"]) {
      await user.type(screen.getByLabelText("Farbe hinzufügen"), color);
      await user.click(screen.getByRole("button", { name: "Farbe dazu" }));
    }
    expect(screen.getByText("Es entstehen 3 Ausführungen.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Anlegen und weiter" }));

    // 3 · Bestand
    expect(await screen.findByRole("heading", { name: /Bestand/ })).toBeInTheDocument();
    const quick = requestsTo(fetchMock, QUICK).map((request) => request.body as QuickEntryIn);
    expect(quick.map((entry) => [entry.product_id, entry.name, entry.finish_code, entry.color, entry.price_cents])).toEqual([
      [null, "IFA W50 Kipper", "unpainted", "", 2500],
      ["p1", null, "painted", "Rot", 4990],
      ["p1", null, "painted", "Blau", 4990],
    ]);
    const kit = screen.getByText("H0 · Bausatz").closest("li") as HTMLElement;
    await user.clear(within(kit).getByLabelText("Anzahl"));
    await user.type(within(kit).getByLabelText("Anzahl"), "2");
    await user.selectOptions(within(kit).getByLabelText("Platz"), "R01-B01");
    await user.click(screen.getByRole("button", { name: "Einbuchen und weiter" }));

    // 4 · Etiketten und Shop
    expect(await screen.findByRole("heading", { name: /Etiketten und Shop/ })).toBeInTheDocument();
    expect(requestsTo(fetchMock, UNITS).map((request) => request.body)).toEqual([
      { variant_id: "v1", quantity: 2, location_code: "R01-B01" },
    ]);
    // The labels of the pieces booked in, ready to print.
    expect(screen.getByText((_, element) => element?.tagName === "P" && element.textContent === "2 Etiketten")).toBeInTheDocument();
    const show = screen.getByRole("checkbox", { name: /Gleich im Shop zeigen/ });
    // Without a photo it does not offer itself.
    expect(show).not.toBeChecked();
    await user.click(show);
    await user.click(screen.getByRole("button", { name: "Fertig" }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/admin/modelle/p1"));
    expect(requestsTo(fetchMock, PUBLISH)).toHaveLength(1);
  });

  it("may skip the stock and needs a place for every number", async () => {
    desk();
    const user = userEvent.setup();
    renderWithQueryClient(<ModelWizard />);
    await user.type(await screen.findByLabelText("Name"), "Lokschuppen");
    await user.click(screen.getByRole("button", { name: "Weiter" }));
    await user.click(screen.getByRole("button", { name: "Anlegen und weiter" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Bitte Maßstab und mindestens eine Ausführung wählen.");
    await user.click(screen.getByRole("radio", { name: /H0/ }));
    await user.click(screen.getByRole("checkbox", { name: "Bausatz" }));
    await user.type(screen.getByLabelText("Preis Bausatz"), "30");
    await user.click(screen.getByRole("button", { name: "Anlegen und weiter" }));

    const count = await screen.findByLabelText("Anzahl");
    await user.clear(count);
    await user.type(count, "1");
    await user.click(screen.getByRole("button", { name: "Einbuchen und weiter" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Bitte zu jeder Anzahl den Platz wählen");
    await user.click(screen.getByRole("button", { name: "Überspringen" }));
    expect(await screen.findByRole("heading", { name: /Etiketten und Shop/ })).toBeInTheDocument();
    expect(requestsTo(fetchMock, UNITS)).toHaveLength(0);
  });

  it("makes nothing twice when a try is repeated after a failure", async () => {
    desk({ quick: 2, units: 2 });
    const user = userEvent.setup();
    renderWithQueryClient(<ModelWizard />);
    await user.type(await screen.findByLabelText("Name"), "Lokschuppen");
    await user.click(screen.getByRole("button", { name: "Weiter" }));
    await user.click(screen.getByRole("radio", { name: /H0/ }));
    await user.click(screen.getByRole("checkbox", { name: "Bausatz" }));
    await user.type(screen.getByLabelText("Preis Bausatz"), "30");
    await user.click(screen.getByRole("checkbox", { name: "Fertigmodell" }));
    await user.type(screen.getByLabelText("Preis Fertigmodell"), "55");

    // The model and its first Ausführung are made, the second fails: again.
    await user.click(screen.getByRole("button", { name: "Anlegen und weiter" }));
    expect(await screen.findByRole("alert")).not.toBeEmptyDOMElement();
    await user.click(screen.getByRole("button", { name: "Anlegen und weiter" }));
    expect(await screen.findByRole("heading", { name: /Bestand/ })).toBeInTheDocument();
    const quick = requestsTo(fetchMock, QUICK).map((request) => request.body as QuickEntryIn);
    expect(quick.map((entry) => [entry.product_id, entry.finish_code])).toEqual([
      [null, "unpainted"],
      ["p1", "painted"],
      ["p1", "painted"],
    ]);

    // The first line is booked in, the second fails: again books only the second.
    for (const label of ["H0 · Bausatz", "H0 · Fertigmodell"]) {
      const line = screen.getByText(label).closest("li") as HTMLElement;
      await user.clear(within(line).getByLabelText("Anzahl"));
      await user.type(within(line).getByLabelText("Anzahl"), "2");
      await user.selectOptions(within(line).getByLabelText("Platz"), "R01-B01");
    }
    await user.click(screen.getByRole("button", { name: "Einbuchen und weiter" }));
    expect(await screen.findByText("2 eingebucht")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Einbuchen und weiter" }));
    expect(await screen.findByRole("heading", { name: /Etiketten und Shop/ })).toBeInTheDocument();
    expect(requestsTo(fetchMock, UNITS).map((request) => (request.body as { variant_id: string }).variant_id)).toEqual(["v1", "v2", "v2"]);
    expect(screen.getByText((_, element) => element?.tagName === "P" && element.textContent === "4 Etiketten")).toBeInTheDocument();
  });

  it("makes one Ausführung per finish, or per colour of a painted one", () => {
    const [kit, painted] = REFERENCES.finishes as [(typeof REFERENCES.finishes)[0], (typeof REFERENCES.finishes)[0]];
    expect(
      plannedVariants(REFERENCES.finishes, {
        unpainted: { chosen: true, price: "25", colors: [], draft: "" },
        painted: { chosen: true, price: "49", colors: ["Rot", "Gelb"], draft: "" },
      }),
    ).toEqual([
      { finish: kit, color: "", price: "25" },
      { finish: painted, color: "Rot", price: "49" },
      { finish: painted, color: "Gelb", price: "49" },
    ]);
  });
});
