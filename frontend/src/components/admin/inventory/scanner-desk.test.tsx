import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ScanIn, ScanOut } from "@/lib/api/generated/model";
import { FakeEventSource } from "@/test/event-source";
import { requestsTo, routeFetch, type RouteRequest } from "@/test/fetch-routes";
import { jsonResponse, renderWithQueryClient } from "@/test/render";

import { ScannerDesk } from "./scanner-desk";

const fetchMock = vi.fn<typeof fetch>();
const SCANS = "POST /api/v1/admin/inventory/scans";
const UNIT = "J4WZXRT2S2";

function answer(scan: ScanIn, change: Partial<ScanOut>): ScanOut {
  return {
    scan_id: scan.scan_id,
    mode: scan.mode,
    outcome: "applied",
    message: "put_away",
    resolved: null,
    unit: null,
    location: null,
    variant: null,
    effect: null,
    progress: null,
    next_expected: null,
    undoable: false,
    undone: false,
    ...change,
  };
}

/** The scan service as the workshop knows it: one compartment, one labelled unit. */
function workshop({ body }: RouteRequest): Response {
  const scan = body as ScanIn;
  if (scan.raw === "R01-F01") {
    return jsonResponse(
      answer(scan, {
        outcome: "selected",
        message: "location_selected",
        resolved: { kind: "location", code: "R01-F01" },
        location: { code: "R01-F01", name: "Fach am Fenster", kind: "compartment", holds_goods: true, unit_count: 0 },
      }),
    );
  }
  return jsonResponse(
    answer(scan, {
      resolved: { kind: "unit", code: UNIT },
      unit: {
        code: UNIT,
        status: "in_stock",
        location_code: "R01-F01",
        variant_id: "v1",
        title: "Stellwerk Altenau · H0 · bemalt",
        sku: "MB-000006-H0-B",
        order_id: null,
        order_number: null,
      },
      effect: {
        unit_code: UNIT,
        from_location: null,
        to_location: "R01-F01",
        from_status: "labeled",
        to_status: "in_stock",
        released_unit: null,
        reserved_for: null,
      },
      undoable: true,
    }),
  );
}

async function scanByHand(user: ReturnType<typeof userEvent.setup>, code: string) {
  const form = screen.getByRole("form", { name: "Code eintippen" });
  await user.type(within(form).getByRole("textbox"), code);
  await user.click(within(form).getByRole("button", { name: "Prüfen" }));
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
});

describe("ScannerDesk", () => {
  it("puts away: the scanned location travels with the units scanned after it", async () => {
    routeFetch(fetchMock, { [SCANS]: workshop });
    const user = userEvent.setup();
    renderWithQueryClient(<ScannerDesk staffRole="packer" initialOrderId={null} onStreamClosed={vi.fn()} />);

    await scanByHand(user, "R01-F01");
    expect(await screen.findByText("Einlagern nach")).toBeInTheDocument();
    await scanByHand(user, UNIT);

    expect(await screen.findByText("Eingelagert.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Rückgängig" })).toBeInTheDocument();
    const sent = requestsTo(fetchMock, SCANS).map((request) => request.body as ScanIn);
    expect(sent.map((scan) => [scan.raw, scan.mode, scan.source, scan.context])).toEqual([
      ["R01-F01", "put_away", "keyboard", {}],
      [UNIT, "put_away", "keyboard", { location_code: "R01-F01" }],
    ]);
  });

  it("keeps scans without network and sends them later with the same id", async () => {
    let online = false;
    routeFetch(fetchMock, {
      [SCANS]: (request) => {
        if (!online) {
          throw new TypeError("Failed to fetch");
        }
        return workshop(request);
      },
    });
    const user = userEvent.setup();
    renderWithQueryClient(<ScannerDesk staffRole="packer" initialOrderId={null} onStreamClosed={vi.fn()} />);

    await scanByHand(user, "R01-F01");
    expect(await screen.findByText(/1 Scan wartet/)).toBeInTheDocument();
    // Offline, the location is taken on trust, so the next units still know where they go.
    expect(screen.getByText("Einlagern nach")).toBeInTheDocument();

    online = true;
    await user.click(screen.getByRole("button", { name: "Jetzt senden" }));
    await waitFor(() => expect(screen.queryByText(/Scan wartet/)).toBeNull());
    const ids = requestsTo(fetchMock, SCANS).map((request) => (request.body as ScanIn).scan_id);
    expect(ids).toHaveLength(2);
    expect(ids[1]).toBe(ids[0]);
  });

  it("refuses what is no store code without asking the server", async () => {
    routeFetch(fetchMock, {});
    const user = userEvent.setup();
    renderWithQueryClient(<ScannerDesk staffRole="packer" initialOrderId={null} onStreamClosed={vi.fn()} />);

    await scanByHand(user, "Hallo Welt");

    expect(await screen.findByText("Das ist kein Code aus dem Lager.")).toBeInTheDocument();
    expect(requestsTo(fetchMock, SCANS)).toHaveLength(0);
  });
});
