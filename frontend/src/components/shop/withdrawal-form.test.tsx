import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { requestsTo, routeFetch } from "@/test/fetch-routes";
import { jsonResponse, renderWithQueryClient } from "@/test/render";

import { WithdrawalForm } from "./withdrawal-form";

const fetchMock = vi.fn<typeof fetch>();
const WITHDRAW = "POST /api/v1/store/withdrawals";

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
});

describe("WithdrawalForm", () => {
  it("withdraws with one confirmation and shows what came in and when", async () => {
    routeFetch(fetchMock, {
      [WITHDRAW]: ({ body }) =>
        jsonResponse({ ...(body as object), received_at: "2026-11-04T14:42:00Z", order_number: "MB-2026-00042" }, 201),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<WithdrawalForm orderNumber="MB-2026-00042" />);

    expect(screen.getByLabelText("Bestellnummer")).toHaveValue("MB-2026-00042");
    await user.type(screen.getByLabelText("Dein Name"), "Erika Mustermann");
    await user.type(screen.getByLabelText("E-Mail-Adresse"), "erika@example.de");
    await user.click(screen.getByRole("button", { name: "Widerruf bestätigen" }));

    expect(await screen.findByText("Dein Widerruf ist eingegangen")).toBeInTheDocument();
    expect(screen.getByText(/Eingegangen am 4\. November 2026 um 15:42 Uhr/)).toBeInTheDocument();
    expect(screen.getByText("die ganze Bestellung")).toBeInTheDocument();
    const [sent] = requestsTo(fetchMock, WITHDRAW);
    expect(sent?.body).toEqual({
      name: "Erika Mustermann",
      order_number: "MB-2026-00042",
      email: "erika@example.de",
      scope: "",
    });
  });

  it("asks for what the confirmation needs before sending anything", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<WithdrawalForm />);

    await user.click(screen.getByRole("button", { name: "Widerruf bestätigen" }));

    await waitFor(() => expect(screen.getByText("Bitte gib deinen Namen ein.")).toBeInTheDocument());
    expect(screen.getByText(/Bitte gib die Bestellnummer ein/)).toBeInTheDocument();
    expect(screen.getByText("Bitte gib eine gültige E-Mail-Adresse ein.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
