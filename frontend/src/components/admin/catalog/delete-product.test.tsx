import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ProductOut } from "@/lib/api/generated/model";
import { requestsTo, routeFetch } from "@/test/fetch-routes";
import { jsonResponse, problemResponse, renderWithQueryClient } from "@/test/render";

import { DeleteProduct } from "./delete-product";

const fetchMock = vi.fn<typeof fetch>();
const replace = vi.fn();

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));

const DELETE = "DELETE /api/v1/admin/products/p7";

function product(overrides: Partial<ProductOut>): ProductOut {
  return {
    id: "p7",
    number: 7,
    name: "Testmodell Stellwerk",
    slug: "testmodell-stellwerk",
    status: "archived",
    summary: "",
    description: "",
    prototype: "",
    primary_category_id: "c1",
    epoch_codes: [],
    scales: [],
    media: [],
    publish_blockers: [],
    published_at: "2026-10-27T10:00:00Z",
    archived_at: "2026-11-10T09:00:00Z",
    created_at: "2026-10-27T10:00:00Z",
    updated_at: "2026-11-10T09:00:00Z",
    version: 9,
    ...overrides,
  };
}

async function openDialog(user: ReturnType<typeof userEvent.setup>): Promise<HTMLElement> {
  await user.click(screen.getByRole("button", { name: "Modell löschen …" }));
  return screen.findByRole("dialog", { name: "„Testmodell Stellwerk“ endgültig löschen?" });
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
  replace.mockReset();
});

describe("DeleteProduct", () => {
  it("deletes an archived model once confirmed, then goes back to the catalogue", async () => {
    routeFetch(fetchMock, { [DELETE]: () => new Response(null, { status: 204 }) });
    const user = userEvent.setup();
    renderWithQueryClient(<DeleteProduct product={product({})} />);

    const dialog = await openDialog(user);
    expect(dialog).toHaveTextContent("Bestellungen behalten ihre eigene Kopie von Name, Preis und Bild.");
    expect(dialog).toHaveTextContent("Das lässt sich nicht rückgängig machen.");
    expect(fetchMock).not.toHaveBeenCalled();

    await user.click(within(dialog).getByRole("button", { name: "Endgültig löschen" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/admin/katalog"));
    expect(requestsTo(fetchMock, DELETE).map((request) => request.headers.get("If-Match"))).toEqual(['"9"']);
  });

  it("offers to delete a draft as well", () => {
    routeFetch(fetchMock, {});
    renderWithQueryClient(<DeleteProduct product={product({ status: "draft", published_at: null, archived_at: null })} />);

    expect(screen.getByRole("button", { name: "Modell löschen …" })).toBeEnabled();
  });

  it("offers no deletion for a model in the shop, only the way there", () => {
    routeFetch(fetchMock, {});
    renderWithQueryClient(<DeleteProduct product={product({ status: "active", archived_at: null })} />);

    expect(screen.queryByRole("button", { name: /löschen/i })).not.toBeInTheDocument();
    expect(screen.getByText("Zum Löschen erst archivieren.")).toBeInTheDocument();
  });

  it("names the open orders that hold the model back", async () => {
    routeFetch(fetchMock, {
      [DELETE]: () =>
        jsonResponse(
          {
            type: "/problems/product-in-open-orders",
            title: "Conflict",
            status: 409,
            detail: "Open orders contain the product: MB-2026-00042, MB-2026-00043.",
            code: "product_in_open_orders",
          },
          409,
          "application/problem+json",
        ),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<DeleteProduct product={product({})} />);

    const dialog = await openDialog(user);
    await user.click(within(dialog).getByRole("button", { name: "Endgültig löschen" }));

    expect(
      await within(dialog).findByText(
        "Bestellungen, die noch auf Zahlung oder Versand warten, enthalten dieses Modell. Solange sie offen sind, lässt es sich nicht löschen.",
      ),
    ).toBeInTheDocument();
    const orders = within(dialog).getByRole("list", { name: "Offene Bestellungen" });
    expect(within(orders).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      "MB-2026-00042",
      "MB-2026-00043",
    ]);
    expect(dialog).not.toHaveTextContent("Open orders");
    expect(replace).not.toHaveBeenCalled();
  });

  it("speaks of the whole model when a bill of materials holds it back", async () => {
    routeFetch(fetchMock, { [DELETE]: () => problemResponse(409, "product_scale_has_bom") });
    const user = userEvent.setup();
    renderWithQueryClient(<DeleteProduct product={product({})} />);

    const dialog = await openDialog(user);
    await user.click(within(dialog).getByRole("button", { name: "Endgültig löschen" }));

    expect(
      await within(dialog).findByText(
        "Für das Modell gibt es in der Fertigung eine Stückliste. Leere sie zuerst, dann lässt es sich löschen.",
      ),
    ).toBeInTheDocument();
    expect(within(dialog).queryByRole("list", { name: "Offene Bestellungen" })).not.toBeInTheDocument();
  });
});
