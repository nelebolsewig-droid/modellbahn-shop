import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { OrderOut } from "@/lib/api/generated/model";
import { requestsTo, routeFetch } from "@/test/fetch-routes";
import { jsonResponse, problemResponse, renderWithQueryClient } from "@/test/render";
import { orderOut } from "@/test/sales";

import { PaymentView } from "./payment-view";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, replace: vi.fn() }) }));
const openPaymentPage = vi.fn();
const reloadPaymentPage = vi.fn();
vi.mock("@/lib/sales/payment-page", () => ({
  openPaymentPage: (url: string) => openPaymentPage(url),
  reloadPaymentPage: () => reloadPaymentPage(),
}));

const fetchMock = vi.fn<typeof fetch>();
const ORDER = "GET /api/v1/store/orders/status-token";
const PAY = "POST /api/v1/store/orders/status-token/payments";
const SYNC = "POST /api/v1/store/orders/status-token/payments/sync";
const PROVIDER = "GET /api/v1/store/payment-provider";
const SUMUP_PAGE = "https://checkout.sumup.com/pay/c-1a2b3c";

function provider(name: "mock" | "sumup" | "off") {
  return () => jsonResponse({ provider: name });
}

const PAYMENT = { amount_cents: 7990, refunded_cents: 0, created_at: "2026-10-25T09:01:00Z", provider: "mock" };
const DECLINED: OrderOut = orderOut({ payments: [{ ...PAYMENT, status: "failed", failure_code: "card_declined" }] });
const PAID: OrderOut = orderOut({
  status: "paid",
  paid_at: "2026-10-25T09:02:00Z",
  payment_due_at: null,
  payments: [
    { ...PAYMENT, status: "failed", failure_code: "card_declined" },
    { ...PAYMENT, created_at: "2026-10-25T09:02:00Z", status: "captured", failure_code: null },
  ],
});

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
  push.mockReset();
  openPaymentPage.mockReset();
  reloadPaymentPage.mockReset();
});

const TRANSFER = {
  account_holder: "adp-Modelle",
  iban: "DE02 1203 0000 0000 2020 51",
  bic: "BYLADEM1001",
  bank_name: "Testbank",
  amount_cents: 7990,
  reference: "MB-2026-00042",
  due_at: "2026-11-04T09:00:00Z",
};

describe("PaymentView with payment in advance", () => {
  it("lets the customer choose a transfer and shows what to transfer", async () => {
    const waiting = orderOut({
      payment_due_at: TRANSFER.due_at,
      payments: [{ ...PAYMENT, provider: "bank_transfer", status: "pending", failure_code: null }],
      bank_transfer: TRANSFER,
    });
    routeFetch(fetchMock, {
      [ORDER]: () => jsonResponse(orderOut()),
      [PROVIDER]: () => jsonResponse({ provider: "sumup", bank_transfer: true }),
      [PAY]: () => jsonResponse(waiting),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<PaymentView token="status-token" />);

    await user.click(await screen.findByRole("radio", { name: /Vorkasse per Überweisung/ }));
    await user.click(screen.getByRole("button", { name: "Per Überweisung bezahlen" }));

    expect(await screen.findByText("DE02 1203 0000 0000 2020 51")).toBeInTheDocument();
    expect(screen.getByText("MB-2026-00042")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /GiroCode/ })).toHaveAttribute(
      "src",
      "/api/v1/store/orders/status-token/girocode.svg",
    );
    expect(requestsTo(fetchMock, PAY)[0]?.body).toEqual({ method: "bank_transfer" });
    expect(openPaymentPage).not.toHaveBeenCalled();
    expect(push).not.toHaveBeenCalled();
  });

  it("offers no choice where the shop takes no transfers", async () => {
    routeFetch(fetchMock, {
      [ORDER]: () => jsonResponse(orderOut()),
      [PROVIDER]: provider("sumup"),
    });
    renderWithQueryClient(<PaymentView token="status-token" />);
    expect(await screen.findByRole("button", { name: /^79,90\s€ bezahlen$/ })).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: /Vorkasse/ })).toBeNull();
  });
});

describe("PaymentView", () => {
  it("tries again with a new key after a declined payment and then shows the order", async () => {
    const answers = [DECLINED, PAID];
    routeFetch(fetchMock, {
      [ORDER]: () => jsonResponse(orderOut()),
      [PROVIDER]: provider("mock"),
      [PAY]: () => jsonResponse(answers.shift()),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<PaymentView token="status-token" />);

    await user.click(await screen.findByRole("radio", { name: /Zahlung wird abgelehnt/ }));
    await user.click(screen.getByRole("button", { name: /^79,90\s€ bezahlen$/ }));
    expect(await screen.findByText(/Die Zahlung wurde abgelehnt/)).toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: /Zahlung gelingt/ }));
    await user.click(screen.getByRole("button", { name: /^79,90\s€ bezahlen$/ }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/bestellung/status-token"));

    const [declined, paid] = requestsTo(fetchMock, PAY);
    expect(declined?.body).toEqual({ method: "declined" });
    expect(paid?.body).toEqual({ method: "succeeds" });
    expect(paid?.headers.get("Idempotency-Key")).not.toBe(declined?.headers.get("Idempotency-Key"));
  });

  it("keeps the order open when the payment provider is down", async () => {
    routeFetch(fetchMock, {
      [ORDER]: () => jsonResponse(orderOut()),
      [PROVIDER]: provider("mock"),
      [PAY]: () => problemResponse(503, "payment_unavailable"),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<PaymentView token="status-token" />);

    await user.click(await screen.findByRole("button", { name: /^79,90\s€ bezahlen$/ }));
    expect(await screen.findByText(/Der Zahlungsdienst ist gerade nicht erreichbar/)).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("offers nothing to pay for an order that is paid already", async () => {
    routeFetch(fetchMock, { [ORDER]: () => jsonResponse(PAID), [PROVIDER]: provider("sumup") });
    renderWithQueryClient(<PaymentView token="status-token" />);

    expect(await screen.findByText("Diese Bestellung ist bezahlt")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /bezahlen/ })).toBeNull();
  });

  describe("with SumUp", () => {
    const SUMUP_PAYMENT = { ...PAYMENT, provider: "sumup" };
    const ON_THE_PAGE: OrderOut = orderOut({
      payment_url: SUMUP_PAGE,
      payments: [{ ...SUMUP_PAYMENT, status: "pending", failure_code: null }],
    });
    const PAID_ON_THE_PAGE: OrderOut = orderOut({
      status: "paid",
      paid_at: "2026-10-25T09:04:00Z",
      payment_due_at: null,
      payments: [{ ...SUMUP_PAYMENT, status: "captured", failure_code: null }],
    });

    it("sends the customer to SumUp's page", async () => {
      routeFetch(fetchMock, {
        [ORDER]: () => jsonResponse(orderOut()),
        [PROVIDER]: provider("sumup"),
        [PAY]: () => jsonResponse(ON_THE_PAGE),
      });
      const user = userEvent.setup();
      renderWithQueryClient(<PaymentView token="status-token" />);

      expect(await screen.findByText("Sicher bezahlen mit SumUp")).toBeInTheDocument();
      expect(screen.queryByRole("radio")).toBeNull();
      await user.click(screen.getByRole("button", { name: /^79,90\s€ bezahlen$/ }));

      await waitFor(() => expect(openPaymentPage).toHaveBeenCalledWith(SUMUP_PAGE));
      expect(screen.getByRole("button", { name: "SumUp wird geöffnet …" })).toBeDisabled();
      const [started] = requestsTo(fetchMock, PAY);
      expect(started?.body).toEqual({ method: "sumup" });
      expect(started?.headers.get("Idempotency-Key")).toBeTruthy();
      expect(requestsTo(fetchMock, SYNC)).toEqual([]);
    });

    it("loads afresh when the browser brings the page back from its cache", async () => {
      routeFetch(fetchMock, { [ORDER]: () => jsonResponse(orderOut()), [PROVIDER]: provider("sumup") });
      renderWithQueryClient(<PaymentView token="status-token" />);
      await screen.findByText("Sicher bezahlen mit SumUp");

      window.dispatchEvent(new PageTransitionEvent("pageshow", { persisted: false }));
      expect(reloadPaymentPage).not.toHaveBeenCalled();
      window.dispatchEvent(new PageTransitionEvent("pageshow", { persisted: true }));
      expect(reloadPaymentPage).toHaveBeenCalledOnce();
    });

    it("asks SumUp on the way back and shows the paid order", async () => {
      routeFetch(fetchMock, {
        [ORDER]: () => jsonResponse(ON_THE_PAGE),
        [PROVIDER]: provider("sumup"),
        [SYNC]: () => jsonResponse(PAID_ON_THE_PAGE),
      });
      renderWithQueryClient(<PaymentView token="status-token" />);

      expect(await screen.findByText(/Wir fragen bei SumUp nach/)).toBeInTheDocument();
      await waitFor(() => expect(push).toHaveBeenCalledWith("/bestellung/status-token"));
      expect(requestsTo(fetchMock, SYNC)).toHaveLength(1);
      expect(requestsTo(fetchMock, PAY)).toEqual([]);
    });

    it("offers the open page again and checks once more on request", async () => {
      const answers = [ON_THE_PAGE, ON_THE_PAGE, PAID_ON_THE_PAGE];
      routeFetch(fetchMock, {
        [ORDER]: () => jsonResponse(ON_THE_PAGE),
        [PROVIDER]: provider("sumup"),
        [SYNC]: () => jsonResponse(answers.shift() ?? PAID_ON_THE_PAGE),
      });
      const user = userEvent.setup();
      renderWithQueryClient(<PaymentView token="status-token" />);

      expect(await screen.findByText("Die Zahlung ist noch nicht abgeschlossen")).toBeInTheDocument();
      expect(screen.getByRole("link", { name: "Weiter zu SumUp" })).toHaveAttribute("href", SUMUP_PAGE);
      await user.click(screen.getByRole("button", { name: "Erneut prüfen" }));
      await user.click(await screen.findByRole("button", { name: "Erneut prüfen" }));
      await waitFor(() => expect(push).toHaveBeenCalledWith("/bestellung/status-token"));
      expect(requestsTo(fetchMock, PAY)).toEqual([]);
    });

    it("says so when SumUp does not answer", async () => {
      routeFetch(fetchMock, {
        [ORDER]: () => jsonResponse(ON_THE_PAGE),
        [PROVIDER]: provider("sumup"),
        [SYNC]: () => problemResponse(503, "payment_unavailable"),
      });
      renderWithQueryClient(<PaymentView token="status-token" />);

      expect(await screen.findByText("SumUp antwortet gerade nicht")).toBeInTheDocument();
      expect(screen.getByRole("link", { name: "Weiter zu SumUp" })).toHaveAttribute("href", SUMUP_PAGE);
      expect(push).not.toHaveBeenCalled();
    });

    it("starts anew after an expired page", async () => {
      const expired = orderOut({ payments: [{ ...SUMUP_PAYMENT, status: "failed", failure_code: "expired" }] });
      routeFetch(fetchMock, { [ORDER]: () => jsonResponse(expired), [PROVIDER]: provider("sumup") });
      renderWithQueryClient(<PaymentView token="status-token" />);

      expect(await screen.findByText(/Die letzte Bezahlseite ist abgelaufen/)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /^79,90\s€ bezahlen$/ })).toBeEnabled();
    });
  });

  it("takes no payment without a provider", async () => {
    routeFetch(fetchMock, { [ORDER]: () => jsonResponse(orderOut()), [PROVIDER]: provider("off") });
    renderWithQueryClient(<PaymentView token="status-token" />);

    expect(await screen.findByText("Bezahlen ist gerade nicht möglich")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /bezahlen/ })).toBeNull();
  });
});
