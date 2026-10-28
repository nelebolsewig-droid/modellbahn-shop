import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AdminFairOut } from "@/lib/api/generated/model";
import { requestsTo, routeFetch } from "@/test/fetch-routes";
import { jsonResponse, problemResponse, renderWithQueryClient } from "@/test/render";

import { FairsManager, splitFairs } from "./fairs-manager";

const fetchMock = vi.fn<typeof fetch>();
const LIST = "GET /api/v1/admin/fairs";
const COUNTS = "GET /api/v1/admin/fair-news";

function fair(overrides: Partial<AdminFairOut>): AdminFairOut {
  return {
    id: "f-dresden",
    name: "Kleinserienmesse Dresden",
    venue: "JohannStadthalle",
    street: "Holbeinstraße 68",
    postal_code: "01307",
    city: "Dresden",
    booth: "",
    hours: "Sa 10–17 Uhr",
    website_url: "",
    note: "",
    starts_on: "2099-11-07",
    ends_on: "2099-11-07",
    when: "7. November 2099",
    published: true,
    announced_at: null,
    created_at: "2026-10-20T10:00:00Z",
    updated_at: "2026-10-20T10:00:00Z",
    ...overrides,
  };
}

const DRESDEN = fair({});
const LEUNA = fair({
  id: "f-leuna",
  name: "Modelltage Leuna",
  city: "Leuna",
  starts_on: "2026-09-12",
  ends_on: "2026-09-13",
  when: "12.–13. September 2026",
});
const DRAFT = fair({ id: "f-draft", name: "Entwurf", published: false, starts_on: "2099-12-01", ends_on: "2099-12-01" });

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
});

describe("splitFairs", () => {
  it("puts the coming fairs first, soonest on top, then the past ones", () => {
    const { upcoming, past } = splitFairs([LEUNA, DRAFT, DRESDEN], "2026-10-28");
    expect(upcoming.map((item) => item.id)).toEqual(["f-dresden", "f-draft"]);
    expect(past.map((item) => item.id)).toEqual(["f-leuna"]);
  });
});

describe("FairsManager", () => {
  it("offers to announce only published fairs still to come", async () => {
    routeFetch(fetchMock, {
      [LIST]: () => jsonResponse({ items: [DRAFT, DRESDEN, LEUNA] }),
      [COUNTS]: () => jsonResponse({ confirmed: 12, pending: 3 }),
    });
    renderWithQueryClient(<FairsManager />);

    const coming = await screen.findByRole("region", { name: "Kommende Messen" });
    const rows = within(coming).getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("Kleinserienmesse Dresden");
    expect(within(rows[0] as HTMLElement).getByRole("button", { name: "Ankündigen" })).toBeInTheDocument();
    expect(rows[1]).toHaveTextContent("Entwurf");
    expect(within(rows[1] as HTMLElement).queryByRole("button", { name: "Ankündigen" })).not.toBeInTheDocument();
    const past = screen.getByRole("region", { name: "Vergangene Messen" });
    expect(within(past).queryByRole("button", { name: "Ankündigen" })).not.toBeInTheDocument();
    expect(await screen.findByText("12")).toBeInTheDocument();
  });

  it("announces after confirming with the number of recipients", async () => {
    routeFetch(fetchMock, {
      [LIST]: () => jsonResponse({ items: [DRESDEN] }),
      [COUNTS]: () => jsonResponse({ confirmed: 12, pending: 0 }),
      "POST /api/v1/admin/fairs/f-dresden/announcement": () =>
        jsonResponse({ fair: { ...DRESDEN, announced_at: "2026-10-28T09:00:00Z" }, recipients: 12 }, 202),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<FairsManager />);
    await screen.findByText("12");

    await user.click(await screen.findByRole("button", { name: "Ankündigen" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("an 12 bestätigte Empfänger");
    await user.click(within(dialog).getByRole("button", { name: "Jetzt senden" }));

    expect(await within(dialog).findByText(/geht jetzt an 12 Empfänger hinaus/)).toBeInTheDocument();
    expect(requestsTo(fetchMock, "POST /api/v1/admin/fairs/f-dresden/announcement")).toHaveLength(1);
    // The answer stays until it is read; then the list shows the fair as announced.
    expect(requestsTo(fetchMock, LIST)).toHaveLength(1);
    await user.click(within(dialog).getByRole("button", { name: "Fertig" }));
    await vi.waitFor(() => expect(requestsTo(fetchMock, LIST)).toHaveLength(2));
  });

  it("does not burn the one announcement on nobody", async () => {
    routeFetch(fetchMock, {
      [LIST]: () => jsonResponse({ items: [DRESDEN] }),
      [COUNTS]: () => jsonResponse({ confirmed: 0, pending: 1 }),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<FairsManager />);
    await screen.findByText("0");

    await user.click(await screen.findByRole("button", { name: "Ankündigen" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Noch hat niemand die Messe-Post bestätigt");
    expect(within(dialog).getByRole("button", { name: "Jetzt senden" })).toBeDisabled();
  });

  it("creates a fair; the last day follows the first", async () => {
    routeFetch(fetchMock, {
      [LIST]: () => jsonResponse({ items: [] }),
      [COUNTS]: () => jsonResponse({ confirmed: 0, pending: 0 }),
      "POST /api/v1/admin/fairs": () => jsonResponse(DRESDEN, 201),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<FairsManager />);

    const form = await screen.findByRole("form", { name: "Neue Messe" });
    await user.type(within(form).getByLabelText("Name"), "Kleinserienmesse Dresden");
    await user.type(within(form).getByLabelText("Erster Tag"), "2099-11-07");
    expect(within(form).getByLabelText("Letzter Tag")).toHaveValue("2099-11-07");
    await user.type(within(form).getByLabelText("Stadt"), "Dresden");
    await user.click(within(form).getByLabelText("Im Shop unter „Termine“ zeigen"));
    await user.click(within(form).getByRole("button", { name: "Messe anlegen" }));

    await vi.waitFor(() => expect(requestsTo(fetchMock, "POST /api/v1/admin/fairs")).toHaveLength(1));
    expect(requestsTo(fetchMock, "POST /api/v1/admin/fairs")[0]?.body).toMatchObject({
      name: "Kleinserienmesse Dresden",
      starts_on: "2099-11-07",
      ends_on: "2099-11-07",
      city: "Dresden",
      published: true,
    });
  });

  it("refuses a last day before the first", async () => {
    routeFetch(fetchMock, {
      [LIST]: () => jsonResponse({ items: [] }),
      [COUNTS]: () => jsonResponse({ confirmed: 0, pending: 0 }),
      "POST /api/v1/admin/fairs": () =>
        problemResponse(422, "validation_failed", [{ field: "ends_on", code: "before_start", message: "x" }]),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<FairsManager />);

    const form = await screen.findByRole("form", { name: "Neue Messe" });
    await user.type(within(form).getByLabelText("Name"), "Leipzig");
    await user.type(within(form).getByLabelText("Erster Tag"), "2099-10-04");
    await user.clear(within(form).getByLabelText("Letzter Tag"));
    await user.type(within(form).getByLabelText("Letzter Tag"), "2099-10-02");
    await user.type(within(form).getByLabelText("Stadt"), "Leipzig");
    await user.click(within(form).getByRole("button", { name: "Messe anlegen" }));

    expect(await within(form).findByText("Der letzte Tag liegt vor dem ersten.")).toBeInTheDocument();
    expect(requestsTo(fetchMock, "POST /api/v1/admin/fairs")).toHaveLength(0);
  });
});
