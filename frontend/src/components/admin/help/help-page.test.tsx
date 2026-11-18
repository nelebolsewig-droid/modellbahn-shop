import { screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { StaffRole } from "@/lib/api/generated/model";
import { routeFetch } from "@/test/fetch-routes";
import { jsonResponse, renderWithQueryClient } from "@/test/render";

import { HANDBOOK_HREF, HelpPage } from "./help-page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => "/admin/hilfe",
}));

const fetchMock = vi.fn<typeof fetch>();

function openAs(role: StaffRole) {
  routeFetch(fetchMock, {
    "GET /api/v1/admin/auth/me": () => jsonResponse({ id: "s1", email: "jana@example.de", display_name: "Jana", role }),
  });
  renderWithQueryClient(<HelpPage />);
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
});

describe("HelpPage", () => {
  it("opens the handbook behind the login", async () => {
    openAs("owner");

    expect(await screen.findByRole("heading", { level: 1, name: "Hilfe" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Handbuch öffnen" })).toHaveAttribute("href", HANDBOOK_HREF);
    expect(HANDBOOK_HREF.startsWith("/admin/")).toBe(true);
  });

  it("shows the office tasks to owner and staff", async () => {
    openAs("staff");

    expect(await screen.findByRole("heading", { name: "Wie lege ich ein neues Modell an?" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Wie versende ich eine Bestellung?" })).toBeInTheDocument();
  });

  it("keeps a packer's list to packing and scanning", async () => {
    openAs("packer");

    expect(await screen.findByRole("heading", { name: "Wie versende ich eine Bestellung?" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Wie lege ich ein neues Modell an?" })).not.toBeInTheDocument();
  });
});
