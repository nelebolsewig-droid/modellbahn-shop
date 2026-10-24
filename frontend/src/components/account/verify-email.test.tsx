import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CUSTOMER_AREA } from "@/lib/navigation";
import { jsonResponse, problemResponse, renderWithQueryClient } from "@/test/render";

import { VerifyEmail } from "./verify-email";

const fetchMock = vi.fn<typeof fetch>();
const replace = vi.fn();

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
  replace.mockReset();
});

const ACCOUNT = {
  id: "0199a8c0-0000-7000-8000-000000000001",
  email: "erika@example.de",
  display_name: "Erika",
  email_verified: true,
};

async function submitPassword(password: string) {
  const user = userEvent.setup();
  renderWithQueryClient(<VerifyEmail token="link-token" />);
  await user.type(screen.getByLabelText("Dein Passwort"), password);
  await user.click(screen.getByRole("button", { name: "E-Mail-Adresse bestätigen" }));
}

function sentBody(): unknown {
  const init = fetchMock.mock.calls[0]?.[1];
  return JSON.parse(String(init?.body));
}

describe("VerifyEmail", () => {
  it("sends nothing before the password is entered", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<VerifyEmail token="link-token" />);
    await user.click(screen.getByRole("button", { name: "E-Mail-Adresse bestätigen" }));

    expect(await screen.findByText("Bitte gib dein Passwort ein.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("redeems the link together with the password and leads to the account", async () => {
    fetchMock.mockResolvedValue(jsonResponse(ACCOUNT));
    await submitPassword("Rangierlok fährt um sechs");

    expect(await screen.findByText("E-Mail-Adresse bestätigt")).toBeInTheDocument();
    expect(sentBody()).toEqual({ token: "link-token", password: "Rangierlok fährt um sechs" });
    expect(replace).toHaveBeenCalledWith(CUSTOMER_AREA.home);
  });

  it("shows a wrong password at the field and keeps the form", async () => {
    fetchMock.mockResolvedValue(problemResponse(400, "invalid_password"));
    await submitPassword("Falsches Passwort 123");

    const field = screen.getByLabelText("Dein Passwort");
    expect(await screen.findByText("Das Passwort ist nicht richtig.")).toBeInTheDocument();
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(replace).not.toHaveBeenCalled();
  });

  it("offers a new link when the old one is used up", async () => {
    fetchMock.mockResolvedValue(problemResponse(400, "invalid_token"));
    await submitPassword("Rangierlok fährt um sechs");

    expect(await screen.findByRole("alert")).toHaveTextContent("Dieser Link ist ungültig");
    expect(screen.getByRole("link", { name: "Neuen Bestätigungslink anfordern" })).toHaveAttribute(
      "href",
      "/konto/bestaetigung-erneut",
    );
  });

  it("asks to wait after too many attempts", async () => {
    fetchMock.mockResolvedValue(problemResponse(429, "too_many_requests"));
    await submitPassword("Rangierlok fährt um sechs");

    expect(await screen.findByRole("alert")).toHaveTextContent("Zu viele Versuche");
  });

  it("explains an incomplete link instead of showing the form", () => {
    renderWithQueryClient(<VerifyEmail token={null} />);

    expect(screen.getByText("Der Link ist unvollständig")).toBeInTheDocument();
    expect(screen.queryByLabelText("Dein Passwort")).not.toBeInTheDocument();
  });
});
