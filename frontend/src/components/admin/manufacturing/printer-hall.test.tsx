import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { HallOut, PrinterDeskOut, PrintJobOut } from "@/lib/api/generated/model";
import { FakeEventSource, latestSource } from "@/test/event-source";
import { requestsTo, routeFetch } from "@/test/fetch-routes";
import { jsonResponse, renderWithQueryClient } from "@/test/render";

import { PrinterHall } from "./printer-hall";

const fetchMock = vi.fn<typeof fetch>();
const BASE = "/api/v1/admin/manufacturing";
const HALL = `GET ${BASE}/hall`;
const JOBS = `GET ${BASE}/print-jobs`;

function job(overrides: Partial<PrintJobOut> = {}): PrintJobOut {
  return {
    id: "j17",
    number: 17,
    printer: { id: "p1", code: "D01", name: "Saturn links" },
    technology: "resin",
    status: "printing",
    planned_minutes: 120,
    expected_end_at: null,
    note: "",
    failure_reason: "",
    part_count: 12,
    created_at: "2026-10-29T07:00:00Z",
    started_at: new Date(Date.now() - 30 * 60_000).toISOString(),
    printed_at: null,
    finished_at: null,
    lines: [
      { part: { id: "dach", part_number: "DACH", name: "Dach", scale_code: "H0" }, quantity: 4, good: 0, failed: 0 },
      {
        part: { id: "sch", part_number: "SCH", name: "Schornstein", scale_code: "H0" },
        quantity: 8,
        good: 0,
        failed: 0,
      },
    ],
    ...overrides,
  };
}

/** Two days and an hour ago, against the real clock the card reads too. */
const TWO_DAYS_AGO = new Date(Date.now() - 49 * 3_600_000).toISOString();

function desk(overrides: Partial<PrinterDeskOut>): PrinterDeskOut {
  return {
    id: "p1",
    code: "D01",
    name: "Saturn links",
    model: "Elegoo Saturn 4 Ultra",
    technology: "resin",
    build_x_mm: null,
    build_y_mm: null,
    build_z_mm: null,
    notes: "",
    status: "in_service",
    status_note: "",
    status_changed_at: TWO_DAYS_AGO,
    created_at: "2026-10-01T07:00:00Z",
    updated_at: "2026-10-01T07:00:00Z",
    printing: null,
    queue: [],
    ...overrides,
  };
}

const WAITING = job({
  id: "j18",
  number: 18,
  status: "queued",
  started_at: null,
  printer: { id: "p2", code: "D02", name: "" },
});

function hall(printers: PrinterDeskOut[]): HallOut {
  return {
    printers,
    post_processing: [],
    counts: {
      in_service: printers.filter((entry) => entry.status === "in_service").length,
      defective: printers.filter((entry) => entry.status === "defective").length,
      in_repair: 0,
      retired: 0,
      printing: printers.filter((entry) => entry.printing !== null).length,
      queued: printers.reduce((sum, entry) => sum + entry.queue.length, 0),
      post_processing: 0,
    },
  };
}

const PRINTERS = [
  desk({ printing: job() }),
  desk({ id: "p2", code: "D02", name: "", queue: [WAITING] }),
  desk({ id: "p3", code: "D03", name: "Mars", status: "defective", status_note: "Folie gerissen" }),
];

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
});

describe("PrinterHall", () => {
  it("shows every printer with its lamp, its plate and what to do next", async () => {
    routeFetch(fetchMock, {
      [HALL]: () => jsonResponse(hall(PRINTERS)),
      [JOBS]: () => jsonResponse({ items: [] }),
    });
    renderWithQueryClient(<PrinterHall staffRole="owner" onStreamClosed={vi.fn()} />);

    const printing = await screen.findByRole("article", { name: /D01/ });
    expect(printing).toHaveTextContent("Druckt");
    expect(printing).toHaveTextContent("Druck 17 · 4 × Dach, 8 × Schornstein");
    expect(within(printing).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "25");
    expect(within(printing).getByRole("button", { name: "Fertig" })).toBeInTheDocument();

    const ready = screen.getByRole("article", { name: /D02/ });
    expect(within(ready).getByRole("button", { name: "Druck 18 starten" })).toBeInTheDocument();

    const broken = screen.getByRole("article", { name: /D03/ });
    expect(broken).toHaveTextContent("Defekt seit 2 Tagen");
    expect(broken).toHaveTextContent("„Folie gerissen“");
    expect(within(broken).getByRole("button", { name: "Wieder in Betrieb" })).toBeInTheDocument();

    const board = screen.getByText("Defekt", { selector: "dt span" }).closest("div");
    expect(board).toHaveTextContent("1");
    expect(screen.getByRole("button", { name: "Druckauftrag planen" })).toBeInTheDocument();
  });

  it("starts the next plate and reloads when the workshop reports something", async () => {
    routeFetch(fetchMock, {
      [HALL]: () => jsonResponse(hall(PRINTERS)),
      [JOBS]: () => jsonResponse({ items: [] }),
      [`POST ${BASE}/print-jobs/j18/start`]: () => jsonResponse({ ...WAITING, status: "printing" }),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<PrinterHall staffRole="packer" onStreamClosed={vi.fn()} />);

    await user.click(await screen.findByRole("button", { name: "Druck 18 starten" }));
    await waitFor(() => expect(requestsTo(fetchMock, `POST ${BASE}/print-jobs/j18/start`)).toHaveLength(1));
    await waitFor(() => expect(requestsTo(fetchMock, HALL)).toHaveLength(2));

    latestSource().emit("manufacturing.printer.status_changed", {
      id: "e1",
      type: "manufacturing.printer.status_changed",
      occurred_at: "2026-10-29T09:00:00Z",
      data: { printer_id: "p3", code: "D03", status: "in_service", previous_status: "defective" },
      truncated: false,
    });
    await waitFor(() => expect(requestsTo(fetchMock, HALL)).toHaveLength(3));
    // Packers work the printers but do not plan.
    expect(screen.queryByRole("button", { name: "Druckauftrag planen" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Drucker hinzufügen" })).not.toBeInTheDocument();
  });

  it("reports the good parts of a plate", async () => {
    routeFetch(fetchMock, {
      [HALL]: () => jsonResponse(hall(PRINTERS)),
      [JOBS]: () => jsonResponse({ items: [] }),
      [`POST ${BASE}/print-jobs/j17/complete`]: () => jsonResponse({ ...job(), status: "done" }),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<PrinterHall staffRole="staff" onStreamClosed={vi.fn()} />);

    const printing = await screen.findByRole("article", { name: /D01/ });
    await user.click(within(printing).getByRole("button", { name: "Fertig" }));
    const dialog = await screen.findByRole("dialog", { name: "Druck 17 fertig melden" });
    const chimneys = within(dialog).getByRole("group", { name: "Gute Teile Schornstein" });
    await user.click(within(chimneys).getByRole("button", { name: "Eins weniger" }));
    expect(dialog).toHaveTextContent("11 von 12 Teilen gut, 1 Ausschuss.");
    await user.click(within(dialog).getByRole("button", { name: "Fertig melden" }));

    await waitFor(() =>
      expect(requestsTo(fetchMock, `POST ${BASE}/print-jobs/j17/complete`)[0]?.body).toEqual({
        lines: [
          { part_id: "dach", good: 4 },
          { part_id: "sch", good: 7 },
        ],
      }),
    );
  });

  it("invites to add the first printer", async () => {
    routeFetch(fetchMock, {
      [HALL]: () => jsonResponse(hall([])),
      [JOBS]: () => jsonResponse({ items: [] }),
    });
    renderWithQueryClient(<PrinterHall staffRole="owner" onStreamClosed={vi.fn()} />);

    expect(await screen.findByRole("heading", { name: "Noch keine Drucker" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ersten Drucker anlegen" })).toBeInTheDocument();
  });
});
