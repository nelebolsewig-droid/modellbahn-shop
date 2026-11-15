import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { requestsTo, routeFetch } from "@/test/fetch-routes";
import { jsonResponse, renderWithQueryClient } from "@/test/render";

import { LeadTimeSettings } from "./lead-time-settings";

const fetchMock = vi.fn<typeof fetch>();
const PRODUCTION = "/api/v1/admin/catalog/production";

function shop(weeks: [number, number]) {
  let current = weeks;
  routeFetch(fetchMock, {
    [`GET ${PRODUCTION}`]: () => jsonResponse({ default_lead_time_min_weeks: current[0], default_lead_time_max_weeks: current[1] }),
    [`PUT ${PRODUCTION}`]: ({ body }) => {
      const sent = body as { default_lead_time_min_weeks: number; default_lead_time_max_weeks: number };
      current = [sent.default_lead_time_min_weeks, sent.default_lead_time_max_weeks];
      return jsonResponse(sent);
    },
  });
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
});

describe("Lieferzeit", () => {
  it("lets the owner change the shop's lead time for every model without its own", async () => {
    shop([2, 4]);
    const user = userEvent.setup();
    renderWithQueryClient(<LeadTimeSettings staffRole="owner" />);

    const from = await screen.findByLabelText("Von (Wochen)");
    expect(from).toHaveValue("2");
    await user.clear(from);
    await user.type(from, "3");
    await user.clear(screen.getByLabelText("Bis (Wochen)"));
    await user.type(screen.getByLabelText("Bis (Wochen)"), "5");
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    expect(await screen.findByText("Gespeichert. Jedes Modell ohne eigene Lieferzeit zeigt jetzt 3–5 Wochen.")).toBeInTheDocument();
    expect(requestsTo(fetchMock, `PUT ${PRODUCTION}`)[0]?.body).toEqual({
      default_lead_time_min_weeks: 3,
      default_lead_time_max_weeks: 5,
    });
  });

  it("refuses a range that ends before it starts, before asking the server", async () => {
    shop([2, 4]);
    const user = userEvent.setup();
    renderWithQueryClient(<LeadTimeSettings staffRole="owner" />);

    const to = await screen.findByLabelText("Bis (Wochen)");
    await user.clear(to);
    await user.type(to, "1");
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    expect(screen.getByRole("alert")).toHaveTextContent("„Von“ darf nicht nach „bis“ liegen.");
    expect(requestsTo(fetchMock, `PUT ${PRODUCTION}`)).toHaveLength(0);
  });

  it("shows staff the lead time without a way to change it", async () => {
    shop([2, 4]);
    renderWithQueryClient(<LeadTimeSettings staffRole="staff" />);

    expect(await screen.findByText("2–4 Wochen")).toBeInTheDocument();
    expect(screen.getByText(/Ändern kann sie nur der Inhaber/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Speichern" })).toBeNull();
  });
});
