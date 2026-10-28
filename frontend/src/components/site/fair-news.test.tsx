import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { requestsTo, routeFetch } from "@/test/fetch-routes";
import { problemResponse, renderWithQueryClient } from "@/test/render";

import { FairNewsForm } from "./fair-news-form";
import { FairNewsLink } from "./fair-news-link";

const fetchMock = vi.fn<typeof fetch>();
const SUBSCRIBE = "POST /api/v1/store/fair-news/subscriptions";
const CONFIRM = "POST /api/v1/store/fair-news/confirmations";
const UNSUBSCRIBE = "POST /api/v1/store/fair-news/unsubscriptions";

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
});

describe("FairNewsForm", () => {
  it("asks for consent before anything is sent", async () => {
    routeFetch(fetchMock, { [SUBSCRIBE]: () => new Response(null, { status: 202 }) });
    const user = userEvent.setup();
    renderWithQueryClient(<FairNewsForm />);

    await user.type(screen.getByLabelText("E-Mail-Adresse"), "erika@example.de");
    await user.click(screen.getByRole("button", { name: "Messe-Post bestellen" }));

    expect(await screen.findByText(/Bitte setz den Haken/)).toBeInTheDocument();
    expect(screen.getByRole("checkbox")).toHaveAttribute("aria-invalid", "true");
    expect(requestsTo(fetchMock, SUBSCRIBE)).toHaveLength(0);
  });

  it("sends address and consent and asks to confirm by mail", async () => {
    routeFetch(fetchMock, { [SUBSCRIBE]: () => new Response(null, { status: 202 }) });
    const user = userEvent.setup();
    renderWithQueryClient(<FairNewsForm />);

    await user.type(screen.getByLabelText("E-Mail-Adresse"), " erika@example.de ");
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Messe-Post bestellen" }));

    expect(await screen.findByText("Fast geschafft – bitte bestätige noch")).toBeInTheDocument();
    expect(screen.getByText("erika@example.de")).toBeInTheDocument();
    expect(requestsTo(fetchMock, SUBSCRIBE).map((request) => request.body)).toEqual([
      { email: "erika@example.de", consent: true },
    ]);
  });

  it("says when there were too many sign-ups", async () => {
    routeFetch(fetchMock, { [SUBSCRIBE]: () => problemResponse(429, "too_many_requests") });
    const user = userEvent.setup();
    renderWithQueryClient(<FairNewsForm />);

    await user.type(screen.getByLabelText("E-Mail-Adresse"), "erika@example.de");
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Messe-Post bestellen" }));

    expect(await screen.findByText(/Zu viele Versuche/)).toBeInTheDocument();
  });
});

describe("FairNewsLink", () => {
  it("confirms only on a click, with the token from the link", async () => {
    routeFetch(fetchMock, { [CONFIRM]: () => new Response(null, { status: 204 }) });
    const user = userEvent.setup();
    renderWithQueryClient(<FairNewsLink action="confirm" token="abc" />);

    expect(requestsTo(fetchMock, CONFIRM)).toHaveLength(0);
    await user.click(screen.getByRole("button", { name: "Messe-Post bestätigen" }));

    expect(await screen.findByText("Du bist dabei")).toBeInTheDocument();
    expect(requestsTo(fetchMock, CONFIRM).map((request) => request.body)).toEqual([{ token: "abc" }]);
  });

  it("explains an expired link", async () => {
    routeFetch(fetchMock, { [CONFIRM]: () => problemResponse(400, "fair_news_token_invalid") });
    const user = userEvent.setup();
    renderWithQueryClient(<FairNewsLink action="confirm" token="alt" />);

    await user.click(screen.getByRole("button", { name: "Messe-Post bestätigen" }));

    expect(await screen.findByText(/Melde dich auf der Terminseite einfach noch einmal an/)).toBeInTheDocument();
  });

  it("unsubscribes with one click", async () => {
    routeFetch(fetchMock, { [UNSUBSCRIBE]: () => new Response(null, { status: 204 }) });
    const user = userEvent.setup();
    renderWithQueryClient(<FairNewsLink action="unsubscribe" token="leave" />);

    await user.click(screen.getByRole("button", { name: "Von der Messe-Post abmelden" }));

    expect(await screen.findByText("Abgemeldet")).toBeInTheDocument();
  });

  it("needs the token", () => {
    renderWithQueryClient(<FairNewsLink action="confirm" token={null} />);
    expect(screen.getByText("Der Link ist unvollständig")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
