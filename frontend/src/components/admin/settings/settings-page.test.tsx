import { screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { StaffRole } from "@/lib/api/generated/model";
import { routeFetch } from "@/test/fetch-routes";
import { jsonResponse, renderWithQueryClient } from "@/test/render";

import { SettingsPage } from "./settings-page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => "/admin/einstellungen",
}));

const fetchMock = vi.fn<typeof fetch>();

function openAs(role: StaffRole) {
  routeFetch(fetchMock, {
    "GET /api/v1/admin/auth/me": () => jsonResponse({ id: "s1", email: "jana@example.de", display_name: "Jana", role }),
  });
  renderWithQueryClient(<SettingsPage />);
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
});

describe("SettingsPage", () => {
  it("leads to the categories, the scales and the eBay setup", async () => {
    openAs("owner");

    expect(await screen.findByRole("heading", { level: 1, name: "Einstellungen" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^Kategorien/ })).toHaveAttribute("href", "/admin/katalog/kategorien");
    expect(screen.getByRole("link", { name: /^Maßstäbe/ })).toHaveAttribute("href", "/admin/katalog/massstaebe");
    expect(screen.getByRole("link", { name: /^eBay-Einrichtung/ })).toHaveAttribute("href", "/admin/einstellungen/ebay");
  });

  it("offers a packer nothing to change", async () => {
    openAs("packer");

    expect(await screen.findByText("Die Einstellungen pflegen Inhaber und Mitarbeiter.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^Kategorien/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^eBay-Einrichtung/ })).not.toBeInTheDocument();
  });
});
