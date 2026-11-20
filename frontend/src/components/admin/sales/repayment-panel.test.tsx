import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { routeFetch } from "@/test/fetch-routes";
import { jsonResponse, renderWithQueryClient } from "@/test/render";

import { RepaymentsPanel } from "./repayment-panel";

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

describe("RepaymentsPanel", () => {
  it("lists what still has to go back, with whether the IBAN is in", async () => {
    routeFetch(fetchMock, {
      "GET /api/v1/admin/repayments": () =>
        jsonResponse({
          items: [
            { order_id: "o3", number: "MB-2026-00003", recipient: "Erika Mustermann", amount_cents: 2590, has_account: false },
            { order_id: "o4", number: "MB-2026-00004", recipient: "Max Muster", amount_cents: 1000, has_account: true },
          ],
        }),
    });
    renderWithQueryClient(<RepaymentsPanel />);

    expect(await screen.findByRole("heading", { name: "Rückzahlungen offen" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "MB-2026-00003" })).toHaveAttribute("href", "/admin/bestellungen/o3");
    expect(screen.getByText("IBAN fehlt noch")).toBeInTheDocument();
    expect(screen.getByText("QR-Code bereit")).toBeInTheDocument();
    expect(screen.getByText(/25,90/)).toBeInTheDocument();
  });

  it("stays out of sight when nothing is open", async () => {
    routeFetch(fetchMock, { "GET /api/v1/admin/repayments": () => jsonResponse({ items: [] }) });
    const { container } = renderWithQueryClient(<RepaymentsPanel />);
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });
});
