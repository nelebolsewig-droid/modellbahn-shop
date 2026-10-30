import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { BomOut, PartOut, PrinterDeskOut, ProductOut } from "@/lib/api/generated/model";
import { requestsTo, routeFetch } from "@/test/fetch-routes";
import { jsonResponse, renderWithQueryClient } from "@/test/render";

import { ProductBomPanel } from "./bom-panel";
import { PlanJobDialog } from "./job-dialogs";

const fetchMock = vi.fn<typeof fetch>();
const BASE = "/api/v1/admin/manufacturing";
const BOM = `${BASE}/product-scales/ps-h0/bom`;
const PARTS = `GET ${BASE}/parts`;

function part(id: string, name: string, overrides: Partial<PartOut> = {}): PartOut {
  return {
    id,
    part_number: id.toUpperCase(),
    name,
    scale_code: "H0",
    scale_name: "H0",
    technology: "resin",
    material: null,
    layer_height_um: 50,
    plate_minutes: 180,
    parts_per_plate: 6,
    minutes_per_part: 30,
    material_per_part: null,
    notes: "",
    active: true,
    bom_count: 0,
    job_count: 0,
    created_at: "2026-10-29T07:00:00Z",
    updated_at: "2026-10-29T07:00:00Z",
    ...overrides,
  };
}

const BODY = part("body", "Gebäude");
const ROOF = part("roof", "Dach", { plate_minutes: 60 });

function bom(lines: BomOut["lines"]): BomOut {
  return {
    product_scale: {
      product_scale_id: "ps-h0",
      product_id: "p1",
      product_number: 42,
      product_name: "Stellwerk Altenau",
      scale_code: "H0",
      scale_name: "H0",
    },
    lines,
    part_count: lines.reduce((sum, line) => sum + line.quantity, 0),
    print_minutes: lines.length ? 90 : null,
    updated_at: lines.length ? "2026-10-29T08:00:00Z" : null,
  };
}

const PRODUCT = {
  id: "p1",
  name: "Stellwerk Altenau",
  scales: [
    { id: "ps-h0", scale_code: "H0", variants: [], length_mm: null, width_mm: null, height_mm: null, weight_g: null },
  ],
} as unknown as ProductOut;

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
});

describe("ProductBomPanel", () => {
  it("lists the parts of a kit like a drawing's parts list", async () => {
    routeFetch(fetchMock, {
      [`GET ${BOM}`]: () =>
        jsonResponse(
          bom([
            { part: BODY, technology: "resin", quantity: 1, plate_minutes: 180, parts_per_plate: 6, active: true },
            { part: ROOF, technology: "resin", quantity: 2, plate_minutes: 60, parts_per_plate: 6, active: true },
          ]),
        ),
    });
    renderWithQueryClient(<ProductBomPanel product={PRODUCT} />);

    const sheet = await screen.findByRole("region", { name: "Stückliste H0" });
    const rows = await within(sheet).findAllByRole("listitem");
    expect(rows.map((row) => row.textContent)).toEqual(["011 ×GebäudeBODY", "022 ×DachROOF"]);
    expect(sheet).toHaveTextContent("3 Teile je Bausatz");
    expect(sheet).toHaveTextContent("etwa 1 h 30 Druckzeit");
  });

  it("puts a kit together from the parts of its scale", async () => {
    routeFetch(fetchMock, {
      [`GET ${BOM}`]: () => jsonResponse(bom([])),
      [PARTS]: () => jsonResponse({ items: [BODY, ROOF] }),
      [`PUT ${BOM}`]: () => jsonResponse(bom([])),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<ProductBomPanel product={PRODUCT} />);

    await user.click(await screen.findByRole("button", { name: "Anlegen" }));
    const offered = await screen.findByRole("list", { name: "Passende Teile" });
    await user.click(within(offered).getByRole("button", { name: /Dach/ }));
    await user.click(
      within(screen.getByRole("list", { name: "Passende Teile" })).getByRole("button", { name: /Gebäude/ }),
    );
    await user.click(
      within(screen.getByRole("group", { name: "Menge Dach" })).getByRole("button", { name: "Eins mehr" }),
    );
    await user.click(screen.getByRole("button", { name: "Stückliste speichern" }));

    await waitFor(() =>
      expect(requestsTo(fetchMock, `PUT ${BOM}`)[0]?.body).toEqual({
        lines: [
          { part_id: "roof", quantity: 2 },
          { part_id: "body", quantity: 1 },
        ],
      }),
    );
    expect(
      new URL(
        String(fetchMock.mock.calls.find(([url]) => String(url).includes("/parts"))?.[0]),
        "http://x",
      ).searchParams.get("scale"),
    ).toBe("H0");
  });
});

describe("PlanJobDialog", () => {
  const PRINTER: PrinterDeskOut = {
    id: "p1",
    code: "D01",
    name: "Saturn links",
    model: "",
    technology: "resin",
    build_x_mm: null,
    build_y_mm: null,
    build_z_mm: null,
    notes: "",
    status: "in_service",
    status_note: "",
    status_changed_at: "2026-10-29T07:00:00Z",
    created_at: "2026-10-29T07:00:00Z",
    updated_at: "2026-10-29T07:00:00Z",
    printing: null,
    queue: [],
  };

  it("queues a plate with an estimate from the parts, or the slicer's time", async () => {
    routeFetch(fetchMock, {
      [PARTS]: () => jsonResponse({ items: [BODY, ROOF] }),
      [`POST ${BASE}/print-jobs`]: () => jsonResponse({}),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<PlanJobDialog printers={[PRINTER]} trigger={<button type="button">Planen</button>} />);

    await user.click(screen.getByRole("button", { name: "Planen" }));
    const dialog = await screen.findByRole("dialog", { name: "Druckauftrag planen" });
    await user.click(await within(dialog).findByRole("button", { name: /Gebäude/ }));
    await user.click(within(dialog).getByRole("button", { name: /Dach/ }));
    expect(dialog).toHaveTextContent("Geschätzt aus den Druckdaten: 3 h.");

    await user.type(within(dialog).getByRole("textbox", { name: /Druckdauer/ }), "3:12");
    await user.click(within(dialog).getByRole("button", { name: "In die Warteschlange" }));

    await waitFor(() =>
      expect(requestsTo(fetchMock, `POST ${BASE}/print-jobs`)[0]?.body).toEqual({
        printer_id: "p1",
        lines: [
          { part_id: "body", quantity: 1 },
          { part_id: "roof", quantity: 1 },
        ],
        planned_minutes: 192,
        note: "",
      }),
    );
  });
});
