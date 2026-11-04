import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type {
  AssemblyPlanOut,
  PartStockLineOut,
  ProductOut,
  ReceiptOut,
  ReferencesOut,
  StockPartOut,
} from "@/lib/api/generated/model";
import { FakeEventSource } from "@/test/event-source";
import { requestsTo, routeFetch } from "@/test/fetch-routes";
import { jsonResponse, renderWithQueryClient } from "@/test/render";

import { AssemblyDesk } from "./assembly-desk";
import { PartStockPanel, ReceivingPanel } from "./parts-panels";

const fetchMock = vi.fn<typeof fetch>();
const INVENTORY = "/api/v1/admin/inventory";

const ROOF: StockPartOut = {
  part_id: "roof",
  part_number: "STW-ALT-DACH-H0",
  name: "Dach",
  scale_code: "H0",
  technology: "resin",
  active: true,
};
const CHIMNEY: StockPartOut = {
  ...ROOF,
  part_id: "chimney",
  part_number: "STW-ALT-SCHORNSTEIN-H0",
  name: "Schornstein",
};

function receipt(id: string, part: StockPartOut, open: number, job = 17): ReceiptOut {
  return {
    id,
    part,
    print_job: { job_id: `j${job}`, number: job, printer_code: "D04", finished_at: new Date().toISOString() },
    quantity: open,
    stored: 0,
    written_off: 0,
    open,
    created_at: new Date().toISOString(),
  };
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
});

describe("ReceivingPanel", () => {
  it("shows one delivery note per plate and writes off what never reached a shelf", async () => {
    routeFetch(fetchMock, {
      [`GET ${INVENTORY}/receiving`]: () =>
        jsonResponse({ items: [receipt("r1", ROOF, 7), receipt("r2", CHIMNEY, 4), receipt("r3", ROOF, 2, 18)] }),
      [`POST ${INVENTORY}/receiving/r2/write-off`]: () => jsonResponse({ ...receipt("r2", CHIMNEY, 0) }),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<ReceivingPanel mayManage />);

    const note = await screen.findByRole("listitem", { name: "Druck 17" });
    expect(note).toHaveTextContent("D04");
    expect(
      within(note)
        .getAllByRole("listitem")
        .map((line) => line.textContent),
    ).toEqual([expect.stringContaining("7Dach"), expect.stringContaining("4Schornstein")]);
    expect(screen.getByRole("listitem", { name: "Druck 18" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Wareneingang · 13 Teile" })).toBeInTheDocument();

    const chimney = within(note).getAllByRole("listitem")[1];
    await user.click(within(chimney as HTMLElement).getByRole("button", { name: "Ausbuchen" }));
    const dialog = await screen.findByRole("dialog", { name: "4 × Schornstein ausbuchen" });
    await user.type(within(dialog).getByRole("textbox", { name: /Grund/ }), "zerbrochen");
    await user.click(within(dialog).getByRole("button", { name: "Ausbuchen" }));

    await waitFor(() =>
      expect(requestsTo(fetchMock, `POST ${INVENTORY}/receiving/r2/write-off`)[0]?.body).toEqual({
        note: "zerbrochen",
      }),
    );
  });

  it("leaves writing off to owner and staff, and says when all is put away", async () => {
    routeFetch(fetchMock, { [`GET ${INVENTORY}/receiving`]: () => jsonResponse({ items: [receipt("r1", ROOF, 7)] }) });
    const { unmount } = renderWithQueryClient(<ReceivingPanel mayManage={false} />);
    expect(await screen.findByRole("button", { name: "Etikett" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ausbuchen" })).not.toBeInTheDocument();
    unmount();

    routeFetch(fetchMock, { [`GET ${INVENTORY}/receiving`]: () => jsonResponse({ items: [] }) });
    renderWithQueryClient(<ReceivingPanel mayManage />);
    expect(await screen.findByText(/Alles eingelagert/)).toBeInTheDocument();
  });
});

describe("PartStockPanel", () => {
  it("lists every part with its boxes and what waits in receiving", async () => {
    const line: PartStockLineOut = {
      part: ROOF,
      total: 12,
      incoming: 7,
      places: [
        { location_code: "R01-F01-B01", location_name: "", quantity: 9 },
        { location_code: "R01-F01-B02", location_name: "", quantity: 3 },
      ],
    };
    routeFetch(fetchMock, { [`GET ${INVENTORY}/parts`]: () => jsonResponse({ items: [line] }) });
    renderWithQueryClient(<PartStockPanel />);

    const places = await screen.findByRole("list", { name: "Plätze Dach" });
    expect(
      within(places)
        .getAllByRole("link")
        .map((link) => link.textContent),
    ).toEqual(["R01-F01-B019", "R01-F01-B023"]);
    expect(screen.getByRole("link", { name: "Dach" })).toHaveAttribute("href", "/admin/lager/teile/STW-ALT-DACH-H0");
    expect(screen.getByText("+7 im Eingang")).toBeInTheDocument();
  });
});

describe("AssemblyDesk", () => {
  const REFERENCES: ReferencesOut = {
    scales: [{ code: "H0", name: "H0", ratio: "1:87", ratio_denominator: 87, track_gauge_mm: 16.5 }],
    finishes: [{ code: "unpainted", name: "Bausatz", sku_letter: "B", colored: false, offered: true }],
    epochs: [],
  };
  const PRODUCT = {
    id: "p1",
    name: "Stellwerk Altenau",
    scales: [
      {
        id: "ps1",
        scale_code: "H0",
        variants: [
          {
            id: "v1",
            finish_code: "unpainted",
            color: "",
            sku: "MB-000042-H0-B",
            price_cents: 2990,
            active: true,
            allow_backorder: true,
          },
        ],
      },
    ],
  } as unknown as ProductOut;

  function plan(quantity: number): AssemblyPlanOut {
    const roofs = { part: ROOF, per_kit: 1, needed: quantity, available: 3, missing: Math.max(0, quantity - 3) };
    const chimneys = {
      part: CHIMNEY,
      per_kit: 2,
      needed: 2 * quantity,
      available: 5,
      missing: Math.max(0, 2 * quantity - 5),
    };
    return {
      variant: {
        variant_id: "v1",
        product_id: "p1",
        product_slug: "stellwerk-altenau",
        title: "Stellwerk Altenau · H0 · Bausatz",
        sku: "MB-000042-H0-B",
        gtin: "2000000000428",
        allow_backorder: true,
      },
      quantity,
      parts: [
        { ...roofs, takes: [{ location_code: "R01-F01-B01", location_name: "", quantity: Math.min(3, quantity) }] },
        {
          ...chimneys,
          takes: [
            { location_code: "R01-F01-B01", location_name: "", quantity: Math.min(3, 2 * quantity) },
            { location_code: "R01-F01-B02", location_name: "", quantity: Math.max(0, Math.min(2, 2 * quantity - 3)) },
          ],
        },
      ],
      possible: 2,
      ready: roofs.missing === 0 && chimneys.missing === 0,
    };
  }

  it("plans from the boxes, books the assembly and offers the labels", async () => {
    routeFetch(fetchMock, {
      ["GET /api/v1/admin/products"]: () =>
        jsonResponse({ items: [{ id: "p1", name: "Stellwerk Altenau", scale_codes: ["H0"], variant_count: 1 }] }),
      ["GET /api/v1/admin/products/p1"]: () => jsonResponse(PRODUCT),
      ["GET /api/v1/admin/catalog/references"]: () => jsonResponse(REFERENCES),
      [`GET ${INVENTORY}/locations`]: () => jsonResponse({ items: [] }),
      [`GET ${INVENTORY}/assembly-plan`]: () => {
        const calls = requestsTo(fetchMock, `GET ${INVENTORY}/assembly-plan`).length;
        return jsonResponse(plan(calls > 1 ? 2 : 1));
      },
      [`POST ${INVENTORY}/assemblies`]: () =>
        jsonResponse({
          plan: plan(2),
          units: [
            { id: "u1", code: "7KQ2X9F4MZ", location: null },
            { id: "u2", code: "J4WZXRT2S2", location: null },
          ],
        }),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<AssemblyDesk staffRole="staff" onStreamClosed={vi.fn()} />);

    await user.click(await screen.findByRole("button", { name: /Stellwerk Altenau/ }));
    await user.click(await screen.findByRole("button", { name: /MB-000042-H0-B/ }));
    expect(await screen.findByText(/Stück aus den Boxen/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Eins mehr" }));

    const chimneys = await screen.findByRole("list", { name: "Entnahme Schornstein" });
    await waitFor(() =>
      expect(
        within(chimneys)
          .getAllByRole("listitem")
          .map((take) => take.textContent),
      ).toEqual(["R01-F01-B01nimm3", "R01-F01-B02nimm1"]),
    );
    expect(screen.getByRole("list", { name: "2 von 2 Stück lassen sich jetzt montieren" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "2 Stück montieren" }));

    await waitFor(() =>
      expect(requestsTo(fetchMock, `POST ${INVENTORY}/assemblies`)[0]?.body).toEqual({
        variant_id: "v1",
        quantity: 2,
        location_code: null,
      }),
    );
    expect(await screen.findByRole("heading", { name: "2 Stück montiert" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "7KQ2 X9F4 MZ" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Weiter montieren" })).toBeInTheDocument();
  });

  it("shows what is missing and does not book a short plan", async () => {
    routeFetch(fetchMock, {
      ["GET /api/v1/admin/products"]: () =>
        jsonResponse({ items: [{ id: "p1", name: "Stellwerk Altenau", scale_codes: ["H0"], variant_count: 1 }] }),
      ["GET /api/v1/admin/products/p1"]: () => jsonResponse(PRODUCT),
      ["GET /api/v1/admin/catalog/references"]: () => jsonResponse(REFERENCES),
      [`GET ${INVENTORY}/locations`]: () => jsonResponse({ items: [] }),
      [`GET ${INVENTORY}/assembly-plan`]: () => jsonResponse(plan(4)),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<AssemblyDesk staffRole="owner" onStreamClosed={vi.fn()} />);

    await user.click(await screen.findByRole("button", { name: /Stellwerk Altenau/ }));
    await user.click(await screen.findByRole("button", { name: /MB-000042-H0-B/ }));

    expect(await screen.findByText("es fehlen 3")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "2 von 4 Stück lassen sich jetzt montieren" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "In der Druckerhalle eine Platte planen" })).toHaveAttribute(
      "href",
      "/admin/fertigung",
    );
    expect(screen.getByRole("button", { name: "1 Stück montieren" })).toBeDisabled();
  });
});
