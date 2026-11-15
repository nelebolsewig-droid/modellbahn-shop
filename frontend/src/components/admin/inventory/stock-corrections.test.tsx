import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type {
  HistoryEntryOut,
  LocatedUnitOut,
  LocationContentsOut,
  LocationNodeOut,
  ProductListItemOut,
  ProductOut,
  ReferencesOut,
  UnitDetailsOut,
  UnitOut,
  UnitStatus,
  VariantRefOut,
} from "@/lib/api/generated/model";
import { checkCharacter, formatUnitCode } from "@/lib/inventory/codes";
import { PROBLEM_MESSAGES } from "@/lib/i18n/problems";
import { FakeEventSource } from "@/test/event-source";
import { requestsTo, routeFetch, type RouteHandler } from "@/test/fetch-routes";
import { jsonResponse, problemResponse, renderWithQueryClient } from "@/test/render";

import { LocationDesk } from "./location-desk";
import { UnitDesk } from "./unit-desk";
import { UnitListDesk } from "./unit-list-desk";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const fetchMock = vi.fn<typeof fetch>();
const INVENTORY = "/api/v1/admin/inventory";
const RESTORES = `POST ${INVENTORY}/units/restores`;
const STOCKTAKE = `POST ${INVENTORY}/locations/R01-F01/stocktakes`;

const STELLWERK: VariantRefOut = {
  variant_id: "v1",
  product_id: "p1",
  product_slug: "stellwerk-altenau",
  title: "Stellwerk Altenau · H0 · Bausatz",
  sku: "MB-000001-H0-B",
  gtin: "2000000000015",
  allow_backorder: false,
};

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

const F01 = place("R01-F01", "LAGER.R01.F01", "compartment");
const F02 = place("R01-F02", "LAGER.R01.F02", "compartment", "Oben");
const TREE = [place("LAGER", "LAGER", "site"), place("R01", "LAGER.R01", "shelf"), F01, F02];

/** A valid unit code from nine characters of the alphabet. */
function unitCode(body: string): string {
  return body + checkCharacter(body);
}

function unit(id: string, status: UnitStatus, location: LocationNodeOut | null = null): UnitOut {
  const code = unitCode(`${id.toUpperCase()}0000000`.slice(0, 9));
  return {
    id,
    code,
    display_code: formatUnitCode(code),
    status,
    variant_id: STELLWERK.variant_id,
    variant: STELLWERK,
    location,
    order_id: status === "allocated" || status === "picked" ? "o7" : null,
    order_number: status === "allocated" || status === "picked" ? "MB-2026-0007" : null,
    scrap_note: status === "scrapped" ? "Inventur Oktober" : "",
    scrap_reason: status === "scrapped" ? "missing" : null,
    created_at: "2026-10-28T10:00:00Z",
    updated_at: "2026-10-28T10:00:00Z",
  };
}

function history(...reasons: HistoryEntryOut["reason"][]): HistoryEntryOut[] {
  return reasons.map((reason, index) => ({
    id: index + 1,
    reason,
    from_status: null,
    to_status: "in_stock",
    from_location_code: null,
    to_location_code: null,
    from_variant: null,
    to_variant: null,
    order_number: null,
    staff_name: null,
    scan_id: null,
    reverses_id: null,
    occurred_at: "2026-10-28T10:00:00Z",
  }));
}

function details(of: UnitOut, reasons: HistoryEntryOut["reason"][] = ["label", "put_away"]): UnitDetailsOut {
  return { ...of, history: history(...reasons), parts: [] };
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
});

describe("Wieder einbuchen", () => {
  function store(units: UnitOut[], extra: Record<string, RouteHandler> = {}) {
    routeFetch(fetchMock, {
      [`GET ${INVENTORY}/units`]: () => jsonResponse({ items: units, more: false }),
      [`GET ${INVENTORY}/stock`]: () => jsonResponse({ items: [] }),
      [`GET ${INVENTORY}/locations`]: () => jsonResponse({ items: TREE }),
      ...extra,
    });
  }

  it("books ticked scrapped pieces in again from the list of scrapped pieces", async () => {
    store([unit("a1", "scrapped"), unit("a2", "scrapped")], {
      [RESTORES]: () => jsonResponse({ restored: 2, already_there: 0, reserved: 1, location: F02 }),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<UnitListDesk variantId="v1" initialFilter="ausgebucht" staffRole="staff" onStreamClosed={() => {}} />);

    expect(await screen.findByText(/Falsch ausgebucht oder doch gefunden\?/)).toBeInTheDocument();
    await user.click(await screen.findByRole("checkbox", { name: "Alle auswählen" }));
    const bar = screen.getByRole("region", { name: "Auswahl" });
    expect(within(bar).queryByRole("button", { name: "Ausbuchen …" })).not.toBeInTheDocument();
    await user.click(within(bar).getByRole("button", { name: "Wieder einbuchen …" }));
    const dialog = await screen.findByRole("dialog", { name: "2 Stücke wieder einbuchen" });
    expect(dialog).toHaveTextContent("Grund und Notiz des Ausbuchens entfallen");
    await user.click(await within(dialog).findByRole("radio", { name: /R01-F02/ }));
    await user.click(within(dialog).getByRole("button", { name: "Hier einbuchen" }));

    await waitFor(() => expect(requestsTo(fetchMock, RESTORES)[0]?.body).toEqual({ unit_ids: ["a1", "a2"], location_code: "R01-F02" }));
    expect(
      await screen.findByText("2 Stücke in R01-F02 wieder eingebucht, 1 davon gleich für eine wartende Bestellung reserviert."),
    ).toHaveAttribute("role", "status");
  });

  it("lets packers look at scrapped pieces but not book them in", async () => {
    store([unit("a1", "scrapped")]);
    renderWithQueryClient(<UnitListDesk variantId="v1" initialFilter="ausgebucht" staffRole="packer" onStreamClosed={() => {}} />);

    const box = await screen.findByRole("checkbox", { name: /A100 0000 0/ });
    expect(box).toBeDisabled();
    expect(box).toHaveAttribute("title", expect.stringContaining("Ausgebucht"));
  });

  it("books a single scrapped piece in again on its page", async () => {
    const scrapped = details(unit("u1", "scrapped"), ["label", "put_away", "scrap"]);
    routeFetch(fetchMock, {
      [`GET ${INVENTORY}/units/${scrapped.code}`]: () => jsonResponse(scrapped),
      [`GET ${INVENTORY}/locations`]: () => jsonResponse({ items: TREE }),
      [RESTORES]: () => jsonResponse({ restored: 1, already_there: 0, reserved: 0, location: F01 }),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<UnitDesk code={scrapped.code} staffRole="owner" onStreamClosed={() => {}} />);

    await user.click(await screen.findByRole("button", { name: "Wieder einbuchen …" }));
    expect(screen.queryByRole("button", { name: "Ausführung ändern …" })).not.toBeInTheDocument();
    const dialog = await screen.findByRole("dialog", { name: `${scrapped.display_code} wieder einbuchen` });
    await user.click(await within(dialog).findByRole("radio", { name: /R01-F01/ }));
    await user.click(within(dialog).getByRole("button", { name: "Hier einbuchen" }));

    await waitFor(() => expect(requestsTo(fetchMock, RESTORES)[0]?.body).toEqual({ unit_ids: ["u1"], location_code: "R01-F01" }));
    expect(await screen.findByText("1 Stück in R01-F01 wieder eingebucht.")).toHaveAttribute("role", "status");
  });
});

describe("Ausführung ändern", () => {
  const REFERENCES: ReferencesOut = {
    scales: [{ code: "H0", name: "H0", ratio: "1:87", ratio_denominator: 87, track_gauge_mm: 16.5 }],
    finishes: [
      { code: "unpainted", name: "Bausatz", sku_letter: "B", colored: false, offered: true },
      { code: "painted", name: "Fertigmodell", sku_letter: "F", colored: true, offered: true },
    ],
    epochs: [],
  };
  const PRODUCT: ProductOut = {
    id: "p1",
    number: 1,
    name: "Stellwerk Altenau",
    slug: "stellwerk-altenau",
    status: "active",
    summary: "",
    description: "",
    prototype: "",
    primary_category_id: null,
    epoch_codes: [],
    scales: [
      {
        id: "s1",
        scale_code: "H0",
        length_mm: null,
        width_mm: null,
        height_mm: null,
        weight_g: null,
        variants: [
          {
            id: "v2",
            finish_code: "painted",
            color: "",
            sku: "MB-000001-H0-F",
            gtin: "2000000000022",
            price_cents: 7990,
            compare_at_price_cents: null,
            active: true,
            allow_backorder: false,
            lead_time_min_weeks: null,
            lead_time_max_weeks: null,
          },
        ],
      },
    ],
    media: [],
    publish_blockers: [],
    published_at: null,
    archived_at: null,
    created_at: "2026-10-28T10:00:00Z",
    updated_at: "2026-10-28T10:00:00Z",
    version: 3,
  };
  const LISTED: ProductListItemOut = {
    id: "p1",
    number: 1,
    name: "Stellwerk Altenau",
    slug: "stellwerk-altenau",
    status: "active",
    main_image: null,
    price_from_cents: 2990,
    published_at: null,
    scale_codes: ["H0"],
    updated_at: "2026-10-28T10:00:00Z",
    variant_count: 2,
  };

  it("changes a free piece to the right Ausführung and offers a new label", async () => {
    const free = details(unit("u1", "in_stock", F01));
    const FERTIG: VariantRefOut = { ...STELLWERK, variant_id: "v2", title: "Stellwerk Altenau · H0 · Fertigmodell", sku: "MB-000001-H0-F", gtin: "2000000000022" };
    const correction = `POST ${INVENTORY}/units/${free.code}/correction`;
    routeFetch(fetchMock, {
      [`GET ${INVENTORY}/units/${free.code}`]: () => jsonResponse(free),
      "GET /api/v1/admin/products": () => jsonResponse({ items: [LISTED], total: 1 }),
      "GET /api/v1/admin/products/p1": () => jsonResponse(PRODUCT),
      "GET /api/v1/admin/catalog/references": () => jsonResponse(REFERENCES),
      [correction]: () => jsonResponse({ ...free, variant_id: "v2", variant: FERTIG }),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<UnitDesk code={free.code} staffRole="staff" onStreamClosed={() => {}} />);

    await user.click(await screen.findByRole("button", { name: "Ausführung ändern …" }));
    const dialog = await screen.findByRole("dialog", { name: `Ausführung von ${free.display_code} ändern` });
    expect(dialog).toHaveTextContent(`Bisher${STELLWERK.title}`);
    expect(within(dialog).getByRole("button", { name: "Ausführung ändern" })).toBeDisabled();
    await user.click(await within(dialog).findByRole("button", { name: /Stellwerk Altenau/ }));
    await user.click(await within(dialog).findByRole("button", { name: /Fertigmodell/ }));
    expect(dialog).toHaveTextContent("Richtig istStellwerk Altenau · H0 · Fertigmodell");
    await user.click(within(dialog).getByRole("button", { name: "Ausführung ändern" }));

    await waitFor(() => expect(requestsTo(fetchMock, correction)[0]?.body).toEqual({ variant_id: "v2" }));
    const done = await screen.findByRole("dialog", { name: "Ausführung geändert" });
    expect(done).toHaveTextContent(`${free.display_code} ist jetzt ${FERTIG.title}.`);
    expect(within(done).getByRole("region", { name: "Etikett neu drucken" })).toBeInTheDocument();
  });

  it("is not offered for a piece that was picked for an order once, nor to packers", async () => {
    const back = details(unit("u1", "in_stock", F01), ["label", "put_away", "allocate", "pick", "release", "put_away"]);
    routeFetch(fetchMock, { [`GET ${INVENTORY}/units/${back.code}`]: () => jsonResponse(back) });
    const { unmount } = renderWithQueryClient(<UnitDesk code={back.code} staffRole="owner" onStreamClosed={() => {}} />);
    expect(await screen.findByRole("button", { name: "Umlagern …" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ausführung ändern …" })).not.toBeInTheDocument();
    unmount();

    const free = details(unit("u2", "in_stock", F01));
    routeFetch(fetchMock, { [`GET ${INVENTORY}/units/${free.code}`]: () => jsonResponse(free) });
    renderWithQueryClient(<UnitDesk code={free.code} staffRole="packer" onStreamClosed={() => {}} />);
    expect(await screen.findByRole("button", { name: "Umlagern …" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ausführung ändern …" })).not.toBeInTheDocument();
  });
});

describe("Inventur", () => {
  function located(of: UnitOut): LocatedUnitOut {
    return {
      id: of.id,
      code: of.code,
      display_code: of.display_code,
      status: of.status,
      variant_id: of.variant_id,
      title: STELLWERK.title,
      sku: STELLWERK.sku,
      location_code: of.location?.code ?? null,
      order_number: of.order_number,
    };
  }

  const A = unit("a1", "in_stock", F01);
  const B = unit("b1", "allocated", F01);
  const C = unit("c1", "in_stock", F01);
  const STRAY = unit("e1", "in_stock", F02);
  const PACKED = unit("f1", "picked");
  const UNKNOWN = unitCode("G10000000");
  const CONTENTS: LocationContentsOut = {
    location: F01,
    ancestors: [],
    children: [],
    units: [A, B, C].map(located),
    parts: [],
  };

  function place_(extra: Record<string, RouteHandler> = {}) {
    routeFetch(fetchMock, {
      [`GET ${INVENTORY}/locations/R01-F01`]: () => jsonResponse(CONTENTS),
      [`GET ${INVENTORY}/locations`]: () => jsonResponse({ items: TREE }),
      [`GET ${INVENTORY}/units/${STRAY.code}`]: () => jsonResponse(details(STRAY)),
      [`GET ${INVENTORY}/units/${PACKED.code}`]: () => jsonResponse(details(PACKED)),
      [`GET ${INVENTORY}/units/${UNKNOWN}`]: () => problemResponse(404, "unit_not_found"),
      ...extra,
    });
  }

  async function scanCode(user: ReturnType<typeof userEvent.setup>, code: string) {
    await user.type(screen.getByRole("textbox", { name: "Code scannen oder eintippen" }), `${code}{Enter}`);
  }

  it("ticks, scans, notes what turned up and books it all in one go", async () => {
    place_({
      [STOCKTAKE]: () => jsonResponse({ confirmed: 2, scrapped: 1, found: 1, reserved: 0, location: F01 }),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<LocationDesk code="R01-F01" staffRole="owner" onStreamClosed={() => {}} />);

    await user.click(await screen.findByRole("button", { name: "Inventur …" }));
    const panel = screen.getByRole("region", { name: "Inventur · R01-F01" });
    expect(screen.queryByRole("region", { name: /Inhalt/ })).not.toBeInTheDocument();
    expect(panel).toHaveTextContent("0 von 3 gezählt");

    await user.click(within(panel).getByRole("checkbox", { name: new RegExp(A.display_code) }));
    await scanCode(user, B.code.toLowerCase());
    expect(within(panel).getByRole("status")).toHaveTextContent(`${B.display_code} gezählt.`);
    await scanCode(user, STRAY.code);
    expect(await within(panel).findByText(`${STRAY.display_code} gefunden (gebucht in R01-F02): wird hier eingelagert.`)).toBeInTheDocument();
    await scanCode(user, PACKED.code);
    expect(await within(panel).findByText(/gehört zu einer Bestellung \(MB-2026-0007\)/)).toBeInTheDocument();
    await scanCode(user, UNKNOWN);
    expect(await within(panel).findByText("Diesen Stück-Code kennt das Lager nicht.")).toBeInTheDocument();
    await scanCode(user, "R01-F02");
    expect(within(panel).getByRole("status")).toHaveTextContent("Das ist ein Platz.");
    expect(panel).toHaveTextContent("2 von 3 gezählt");
    expect(panel).toHaveTextContent("Gefunden · 1 Stück");

    await user.click(within(panel).getByRole("button", { name: "Abschließen …" }));
    const summary = await screen.findByRole("dialog", { name: "Inventur R01-F01 abschließen" });
    expect(summary).toHaveTextContent("2 bestätigt");
    expect(summary).toHaveTextContent("1 fehlen → werden ausgebucht mit Grund „Fehlt bei Inventur“.");
    expect(summary).toHaveTextContent(C.display_code);
    expect(summary).toHaveTextContent("1 gefunden → werden hier eingelagert.");
    expect(requestsTo(fetchMock, STOCKTAKE)).toHaveLength(0);
    await user.click(within(summary).getByRole("button", { name: "Inventur buchen" }));

    await waitFor(() =>
      expect(requestsTo(fetchMock, STOCKTAKE)[0]?.body).toEqual({
        present_unit_ids: ["a1", "b1"],
        missing_unit_ids: ["c1"],
        found_unit_ids: ["e1"],
      }),
    );
    expect(await screen.findByText("Inventur R01-F01 gebucht: 2 bestätigt, 1 Stück ausgebucht, 1 Stück hier eingelagert.")).toHaveAttribute(
      "role",
      "status",
    );
    expect(screen.queryByRole("region", { name: "Inventur · R01-F01" })).not.toBeInTheDocument();
  });

  it("says that a missing reserved piece frees its order, and keeps the count when the place changed", async () => {
    place_({ [STOCKTAKE]: () => problemResponse(409, "stocktake_outdated") });
    const user = userEvent.setup();
    renderWithQueryClient(<LocationDesk code="R01-F01" staffRole="staff" onStreamClosed={() => {}} />);

    await user.click(await screen.findByRole("button", { name: "Inventur …" }));
    const panel = screen.getByRole("region", { name: "Inventur · R01-F01" });
    await user.click(within(panel).getByRole("checkbox", { name: new RegExp(A.display_code) }));
    await user.click(within(panel).getByRole("button", { name: "Abschließen …" }));
    const summary = await screen.findByRole("dialog", { name: "Inventur R01-F01 abschließen" });
    expect(summary).toHaveTextContent("Eins davon ist reserviert: Die Bestellung bekommt ein anderes Stück oder wartet auf die Fertigung.");
    await user.click(within(summary).getByRole("button", { name: "Inventur buchen" }));

    expect(await within(summary).findByRole("alert")).toHaveTextContent(PROBLEM_MESSAGES.stocktake_outdated as string);
    await user.click(within(summary).getByRole("button", { name: "Weiter zählen" }));
    expect(within(panel).getByRole("checkbox", { name: new RegExp(A.display_code) })).toBeChecked();
  });

  it("is for owner and staff only", async () => {
    place_();
    renderWithQueryClient(<LocationDesk code="R01-F01" staffRole="packer" onStreamClosed={() => {}} />);
    expect(await screen.findByRole("region", { name: /Inhalt/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Inventur …" })).not.toBeInTheDocument();
  });
});
