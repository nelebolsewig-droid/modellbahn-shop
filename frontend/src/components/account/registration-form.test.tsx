import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, problemResponse, renderWithQueryClient } from "@/test/render";

import { RegistrationForm } from "./registration-form";

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
});

function setup() {
  const user = userEvent.setup();
  renderWithQueryClient(<RegistrationForm />);
  return {
    user,
    name: screen.getByLabelText("Name"),
    email: screen.getByLabelText("E-Mail-Adresse"),
    password: screen.getByLabelText("Passwort"),
    submit: screen.getByRole("button", { name: "Konto anlegen" }),
  };
}

describe("RegistrationForm", () => {
  it("explains in German what is missing, without calling the API", async () => {
    const { user, name, email, password, submit } = setup();
    await user.click(submit);

    expect(await screen.findByText("Bitte gib einen Namen ein.")).toBeInTheDocument();
    expect(screen.getByText("Bitte gib deine E-Mail-Adresse ein.")).toBeInTheDocument();
    expect(screen.getByText("Bitte gib ein Passwort ein.")).toBeInTheDocument();
    for (const field of [name, email, password]) {
      expect(field).toHaveAttribute("aria-invalid", "true");
    }
    expect(name).toHaveFocus();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("ties each message to its field for screen readers", async () => {
    const { user, password, submit } = setup();
    await user.click(submit);

    const message = await screen.findByText("Bitte gib ein Passwort ein.");
    expect(message).toHaveAttribute("aria-live", "polite");
    expect(password.getAttribute("aria-describedby")?.split(" ")).toContain(message.id);
    // The hint stays referenced next to the error.
    expect(password).toHaveAccessibleDescription(/Mindestens 10 Zeichen/);
  });

  it("checks address, length and the password rule as the user leaves a field", async () => {
    const { user, email, password } = setup();
    await user.type(email, "erika@");
    await user.tab();
    expect(await screen.findByText("Bitte gib eine gültige E-Mail-Adresse ein.")).toBeInTheDocument();

    await user.type(password, "kurz");
    await user.tab();
    expect(
      await screen.findByText("Das Passwort muss mindestens 10 Zeichen lang sein."),
    ).toBeInTheDocument();

    await user.clear(email);
    await user.type(email, "erika@example.de");
    await user.clear(password);
    await user.type(password, "ERIKA@example.de");
    await user.click(screen.getByRole("button", { name: "Konto anlegen" }));
    expect(
      await screen.findByText("Das Passwort darf nicht deine E-Mail-Adresse sein."),
    ).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("registers and then asks the user to check the inbox", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: "pending_verification" }, 202));
    const { user, name, email, password, submit } = setup();
    await user.type(name, "  Erika   Mustermann ");
    await user.type(email, "erika@example.de");
    await user.type(password, "Rangierlok fährt um sechs");
    await user.click(submit);

    const result = await screen.findByRole("status");
    expect(result).toHaveTextContent("Bitte schau in dein Postfach");
    expect(result).toHaveTextContent("erika@example.de");
    expect(result).toHaveFocus();

    const [url, init] = fetchMock.mock.lastCall ?? [];
    expect(url).toBe("/api/v1/store/account/register");
    expect(init?.method).toBe("POST");
    expect(new Headers(init?.headers).get("X-Modellbahn-Client")).toBe("web");
    expect(JSON.parse(String(init?.body))).toEqual({
      display_name: "Erika Mustermann",
      email: "erika@example.de",
      password: "Rangierlok fährt um sechs",
    });
  });

  it("shows the backend's field errors in German at the field", async () => {
    fetchMock.mockResolvedValue(
      problemResponse(422, "validation_failed", [
        { field: "email", code: "invalid", message: "value is not a valid email address" },
      ]),
    );
    const { user, name, email, password, submit } = setup();
    await user.type(name, "Erika");
    await user.type(email, "erika@example.de");
    await user.type(password, "Rangierlok fährt um sechs");
    await user.click(submit);

    expect(await screen.findByText("Bitte gib eine gültige E-Mail-Adresse ein.")).toBeInTheDocument();
    expect(screen.queryByText(/not a valid email/)).not.toBeInTheDocument();
    await waitFor(() => expect(email).toHaveFocus());
  });

  it("shows other failures above the form", async () => {
    fetchMock.mockResolvedValue(problemResponse(403, "csrf_header_missing"));
    const { user, name, email, password, submit } = setup();
    await user.type(name, "Erika");
    await user.type(email, "erika@example.de");
    await user.type(password, "Rangierlok fährt um sechs");
    await user.click(submit);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Die Anfrage wurde aus Sicherheitsgründen abgelehnt.",
    );
    expect(submit).toBeEnabled();
  });
});
