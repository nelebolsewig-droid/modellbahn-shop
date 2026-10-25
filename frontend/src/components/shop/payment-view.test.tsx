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

const fetchMock = vi.fn<typeof fetch>();
const PAY = "POST /api/v1/store/orders/status-token/payments";

const PAYMENT = { amount_cents: 7990, created_at: "2026-10-25T09:01:00Z", provider: "mock" };
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
});

describe("PaymentView", () => {
  it("tries again with a new key after a declined payment and then shows the order", async () => {
    const answers = [DECLINED, PAID];
    routeFetch(fetchMock, {
      "GET /api/v1/store/orders/status-token": () => jsonResponse(orderOut()),
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
      "GET /api/v1/store/orders/status-token": () => jsonResponse(orderOut()),
      [PAY]: () => problemResponse(503, "payment_unavailable"),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<PaymentView token="status-token" />);

    await user.click(await screen.findByRole("button", { name: /^79,90\s€ bezahlen$/ }));
    expect(await screen.findByText(/Der Zahlungsdienst ist gerade nicht erreichbar/)).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("offers nothing to pay for an order that is paid already", async () => {
    routeFetch(fetchMock, { "GET /api/v1/store/orders/status-token": () => jsonResponse(PAID) });
    renderWithQueryClient(<PaymentView token="status-token" />);

    expect(await screen.findByText("Diese Bestellung ist bezahlt")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /bezahlen/ })).toBeNull();
  });
});
