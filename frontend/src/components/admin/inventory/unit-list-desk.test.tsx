import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type {
  LocationNodeOut,
  StockLineOut,
  UnitDetailsOut,
  UnitOut,
  UnitStatus,
  VariantRefOut,
} from "@/lib/api/generated/model";
import { PROBLEM_MESSAGES } from "@/lib/i18n/problems";
import { FakeEventSource } from "@/test/event-source";
import { requestsTo, routeFetch, type RouteHandler } from "@/test/fetch-routes";
import { jsonResponse, problemResponse, renderWithQueryClient } from "@/test/render";

import { UnitDesk } from "./unit-desk";
import { UnitListDesk } from "./unit-list-desk";

const fetchMock = vi.fn<typeof fetch>();
const INVENTORY = "/api/v1/admin/inventory";
const MOVES = `POST ${INVENTORY}/units/moves`;
const SCRAPS = `POST ${INVENTORY}/units/scraps`;

const STELLWERK: VariantRefOut = {
  variant_id: "v1",
  product_id: "p1",
  product_slug: "stellwerk-altenau",
  title: "Stellwerk Altenau · H0 · Bausatz",
  sku: "MB-000001-H0-B",
  gtin: "2000000000015",
  allow_backorder: false,
};
const LOKSCHUPPEN: VariantRefOut = { ...STELLWERK, variant_id: "v2", title: "Lokschuppen · H0 · Bausatz", sku: "MB-000002-H0-B" };

function place(code: string, path: string, kind: LocationNodeOut["kind"], name = ""): LocationNodeOut {
  return {
    id: `l-${code}`,
    code,
    path,
    kind,
    name,
    parent_id: null,
    holds_goods: kind === "compartment" || kind === "box" || kind === "staging",
    depth: path.split(".").length - 1,
    unit_count: 0,
    total_count: 0,
    part_count: 0,
  };
}

const TREE = [
  place("LAGER", "LAGER", "site"),
  place("R01", "LAGER.R01", "shelf"),
  place("R01-F01", "LAGER.R01.F01", "compartment"),
  place("R01-F02", "LAGER.R01.F02", "compartment", "Oben"),
  place("PACK", "LAGER.PACK", "staging", "Packtisch"),
];

function unit(id: string, status: UnitStatus, variant: VariantRefOut = STELLWERK): UnitOut {
  const code = `${id.toUpperCase().padEnd(8, "X")}MZ`;
  const stored = status === "in_stock" || status === "allocated";
  return {
    id,
    code,
    display_code: `${code.slice(0, 4)} ${code.slice(4, 8)} ${code.slice(8)}`,
    status,
    variant_id: variant.variant_id,
    variant,
    location: stored ? { ...(TREE[2] as LocationNodeOut) } : null,
    order_id: null,
    order_number: status === "picked" ? "MB-2026-0007" : null,
    scrap_note: "",
    scrap_reason: null,
    created_at: "2026-10-28T10:00:00Z",
    updated_at: "2026-10-28T10:00:00Z",
  };
}

function line(variant: VariantRefOut, counts: Partial<StockLineOut>): StockLineOut {
  return { variant_id: variant.variant_id, variant, labeled: 0, in_stock: 0, allocated: 0, picked: 0, backordered: 0, ...counts };
}

function store(units: UnitOut[], stock: StockLineOut[], extra: Record<string, RouteHandler> = {}) {
  routeFetch(fetchMock, {
    [`GET ${INVENTORY}/units`]: () => jsonResponse({ items: units, more: false }),
    [`GET ${INVENTORY}/stock`]: () => jsonResponse({ items: stock }),
    [`GET ${INVENTORY}/locations`]: () => jsonResponse({ items: TREE }),
    ...extra,
  });
}

/** The query strings of the list requests, in order. */
function listQueries(): string[] {
  return fetchMock.mock.calls
    .map(([input]) => new URL(String(input), "http://shop.test"))
    .filter((url) => url.pathname === `${INVENTORY}/units`)
    .map((url) => url.search);
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
});

describe("UnitListDesk", () => {
  it("ticks two pieces of an article and moves them to the chosen place", async () => {
    const units = [unit("a1", "in_stock"), unit("a2", "allocated"), unit("a3", "picked")];
    store(units, [line(STELLWERK, { in_stock: 1, allocated: 1, picked: 1 })], {
      [MOVES]: () =>
        jsonResponse({ moved: 1, already_there: 1, location: { ...(TREE[3] as LocationNodeOut) } }),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<UnitListDesk variantId="v1" initialFilter={null} staffRole="packer" onStreamClosed={() => {}} />);

    expect(await screen.findByRole("heading", { level: 1, name: STELLWERK.title })).toBeInTheDocument();
    const picked = await screen.findByRole("checkbox", { name: /A3XX XXXX MZ/ });
    expect(picked).toBeDisabled();
    expect(picked).toHaveAttribute("title", expect.stringContaining("Kommissioniert"));
    expect(listQueries()[0]).toBe("?variant_id=v1&status=labeled&status=in_stock&status=allocated&status=picked");

    await user.click(screen.getByRole("checkbox", { name: "A1XX XXXX MZ auswählen" }));
    await user.click(screen.getByRole("checkbox", { name: "A2XX XXXX MZ auswählen" }));
    const bar = screen.getByRole("region", { name: "Auswahl" });
    expect(bar).toHaveTextContent("2 Stücke ausgewählt");
    // Packers move pieces like they do with the scanner, but take nothing out of the stock.
    expect(within(bar).queryByRole("button", { name: "Ausbuchen …" })).not.toBeInTheDocument();

    await user.click(within(bar).getByRole("button", { name: "Umlagern …" }));
    const dialog = await screen.findByRole("dialog", { name: "2 Stücke umlagern" });
    await user.type(within(dialog).getByRole("searchbox", { name: "Platz suchen" }), "oben");
    expect(within(dialog).getAllByRole("radio")).toHaveLength(1);
    const target = within(dialog).getByRole("radio", { name: /R01-F02/ });
    expect(target).toHaveAccessibleName(expect.stringContaining("LAGER › R01 › F02"));
    await user.click(target);
    await user.click(within(dialog).getByRole("button", { name: "Hierher umlagern" }));

    await waitFor(() => expect(requestsTo(fetchMock, MOVES)[0]?.body).toEqual({ unit_ids: ["a1", "a2"], location_code: "R01-F02" }));
    expect(await screen.findByText("1 Stück nach R01-F02 umgelagert, 1 lag schon dort.")).toHaveAttribute("role", "status");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Auswahl" })).not.toBeInTheDocument();
  });

  it("keeps the dialog open with the German reason when the backend refuses", async () => {
    store([unit("a1", "in_stock")], [line(STELLWERK, { in_stock: 1 })], {
      [MOVES]: () => problemResponse(409, "units_not_movable"),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<UnitListDesk variantId="v1" initialFilter={null} staffRole="owner" onStreamClosed={() => {}} />);

    await user.click(await screen.findByRole("checkbox", { name: "A1XX XXXX MZ auswählen" }));
    await user.click(screen.getByRole("button", { name: "Umlagern …" }));
    const dialog = await screen.findByRole("dialog", { name: "A1XX XXXX MZ umlagern" });
    await user.click(await within(dialog).findByRole("radio", { name: /PACK/ }));
    await user.click(within(dialog).getByRole("button", { name: "Hierher umlagern" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(PROBLEM_MESSAGES.units_not_movable as string);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("lists every unbooked piece by article and stores them all in one go", async () => {
    const units = [unit("b1", "labeled"), unit("b2", "labeled", LOKSCHUPPEN), unit("b3", "labeled")];
    store(units, [line(STELLWERK, { labeled: 2, in_stock: 4 }), line(LOKSCHUPPEN, { labeled: 1 })], {
      [MOVES]: () => jsonResponse({ moved: 3, already_there: 0, location: { ...(TREE[2] as LocationNodeOut) } }),
    });
    const user = userEvent.setup();
    renderWithQueryClient(
      <UnitListDesk variantId={null} initialFilter="unverbucht" staffRole="owner" onStreamClosed={() => {}} />,
    );

    const groups = await screen.findAllByRole("region", { name: /Bausatz/ });
    expect(groups.map((group) => group.getAttribute("aria-label"))).toEqual([LOKSCHUPPEN.title, STELLWERK.title]);
    expect(within(groups[1] as HTMLElement).getAllByText("nie eingelagert")).toHaveLength(2);
    expect(screen.getByRole("radio", { name: /Unverbucht/ })).toBeChecked();
    expect(listQueries()[0]).toBe("?status=labeled");

    await user.click(screen.getByRole("checkbox", { name: "Alle auswählen" }));
    const bar = screen.getByRole("region", { name: "Auswahl" });
    expect(bar).toHaveTextContent("3 Stücke ausgewählt");
    await user.click(within(bar).getByRole("button", { name: "Einlagern …" }));
    const dialog = await screen.findByRole("dialog", { name: "3 Stücke einlagern" });
    expect(dialog).toHaveTextContent("Danach sind sie im Shop lieferbar.");
    await user.click(await within(dialog).findByRole("radio", { name: /R01-F01/ }));
    await user.click(within(dialog).getByRole("button", { name: "Hier einlagern" }));

    await waitFor(() => expect(requestsTo(fetchMock, MOVES)[0]?.body).toEqual({ unit_ids: ["b1", "b2", "b3"], location_code: "R01-F01" }));
    expect(await screen.findByText("3 Stücke in R01-F01 eingelagert. Sie sind jetzt im Shop lieferbar.")).toHaveAttribute("role", "status");
  });

  it("takes ticked pieces out of the stock with a reason", async () => {
    store([unit("c1", "in_stock"), unit("c2", "labeled")], [line(STELLWERK, { in_stock: 1, labeled: 1 })], {
      [SCRAPS]: () => jsonResponse({ scrapped: 2, already_scrapped: 0 }),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<UnitListDesk variantId="v1" initialFilter={null} staffRole="staff" onStreamClosed={() => {}} />);

    expect(await screen.findByText(/1 Stück unverbucht:/)).toBeInTheDocument();
    await user.click(await screen.findByRole("checkbox", { name: "Alle auswählen" }));
    const bar = screen.getByRole("region", { name: "Auswahl" });
    expect(within(bar).getByRole("button", { name: "Umlagern …" })).toBeInTheDocument();
    await user.click(within(bar).getByRole("button", { name: "Ausbuchen …" }));
    const dialog = await screen.findByRole("dialog", { name: "2 Stücke ausbuchen" });
    await user.click(within(dialog).getByRole("button", { name: "Ausbuchen" }));
    expect(within(dialog).getByText("Bitte einen Grund wählen.")).toBeInTheDocument();
    expect(requestsTo(fetchMock, SCRAPS)).toHaveLength(0);

    await user.click(within(dialog).getByRole("radio", { name: "Fehlt bei Inventur" }));
    await user.type(within(dialog).getByRole("textbox", { name: /Notiz/ }), "Inventur Oktober");
    await user.click(within(dialog).getByRole("button", { name: "Ausbuchen" }));

    await waitFor(() =>
      expect(requestsTo(fetchMock, SCRAPS)[0]?.body).toEqual({ unit_ids: ["c1", "c2"], reason: "missing", note: "Inventur Oktober" }),
    );
    expect(await screen.findByText("2 Stücke ausgebucht (Fehlt bei Inventur).")).toHaveAttribute("role", "status");
  });
});

describe("UnitDesk", () => {
  const CODE = "7KQ2X9F4MZ";
  const DETAILS: UnitDetailsOut = { ...unit("u1", "labeled"), code: CODE, display_code: "7KQ2 X9F4 MZ", history: [], parts: [] };

  it("stores a single labelled piece and takes a piece out with a reason", async () => {
    routeFetch(fetchMock, {
      [`GET ${INVENTORY}/units/${CODE}`]: () => jsonResponse(DETAILS),
      [`GET ${INVENTORY}/locations`]: () => jsonResponse({ items: TREE }),
      [MOVES]: () => jsonResponse({ moved: 1, already_there: 0, location: { ...(TREE[2] as LocationNodeOut) } }),
      [`POST ${INVENTORY}/units/${CODE}/scrap`]: () => jsonResponse({ ...DETAILS, status: "scrapped", scrap_reason: "sold" }),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<UnitDesk code={CODE} staffRole="owner" onStreamClosed={() => {}} />);

    expect(await screen.findByText("nie eingelagert")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Einlagern …" }));
    const move = await screen.findByRole("dialog", { name: "7KQ2 X9F4 MZ einlagern" });
    await user.click(await within(move).findByRole("radio", { name: /R01-F01/ }));
    await user.click(within(move).getByRole("button", { name: "Hier einlagern" }));
    await waitFor(() => expect(requestsTo(fetchMock, MOVES)[0]?.body).toEqual({ unit_ids: ["u1"], location_code: "R01-F01" }));
    expect(await screen.findByText("1 Stück in R01-F01 eingelagert. Es ist jetzt im Shop lieferbar.")).toHaveAttribute("role", "status");

    await user.click(screen.getByRole("button", { name: "Ausbuchen …" }));
    const scrap = await screen.findByRole("dialog", { name: "7KQ2 X9F4 MZ ausbuchen?" });
    await user.click(within(scrap).getByRole("radio", { name: "Verkauft (Messe, Laden, privat)" }));
    await user.click(within(scrap).getByRole("button", { name: "Ausbuchen" }));
    await waitFor(() =>
      expect(requestsTo(fetchMock, `POST ${INVENTORY}/units/${CODE}/scrap`)[0]?.body).toEqual({ reason: "sold", note: "" }),
    );
  });
});
