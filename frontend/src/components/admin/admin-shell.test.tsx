import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { StaffOut, StaffRole } from "@/lib/api/generated/model";
import { routeFetch } from "@/test/fetch-routes";
import { jsonResponse, renderWithQueryClient } from "@/test/render";

import { AdminShell } from "./admin-shell";

const navigation = vi.hoisted(() => ({ pathname: "/admin" }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => navigation.pathname,
}));

const fetchMock = vi.fn<typeof fetch>();

function staff(role: StaffRole): StaffOut {
  return { id: "s1", email: "jana@example.de", display_name: "Jana", role };
}

async function openShell(role: StaffRole, pathname: string, toMake = 0) {
  navigation.pathname = pathname;
  routeFetch(fetchMock, {
    "GET /api/v1/admin/auth/me": () => jsonResponse(staff(role)),
    "GET /api/v1/admin/inventory/stock/to-make": () => jsonResponse({ items: [], quantity: toMake }),
  });
  renderWithQueryClient(
    <AdminShell>
      <p>Seiteninhalt</p>
    </AdminShell>,
  );
  await screen.findByText("Seiteninhalt");
  // Both navigations are in the page; CSS shows the header's on a desk, the bar on the phone.
  const [header, bar] = screen.getAllByRole("navigation", { name: "Stellwerk" });
  if (header === undefined || bar === undefined) {
    throw new Error("expected the header navigation and the phone bar");
  }
  return { header, bar };
}

const linkNames = (element: HTMLElement) => within(element).getAllByRole("link").map((link) => link.textContent);

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
});

describe("AdminShell", () => {
  it("shows a packer Bestellungen, Lager and Scannen, the rest behind Mehr", async () => {
    const user = userEvent.setup();
    const { header, bar } = await openShell("packer", "/admin/lager");

    expect(linkNames(header)).toEqual(["Bestellungen", "Lager", "Fertigung"]);
    expect(within(header).getByRole("link", { name: "Lager" })).toHaveAttribute("aria-current", "page");
    expect(screen.getAllByRole("link", { name: "Scannen" })[0]).toHaveAttribute("href", "/admin/scanner");
    for (const hidden of ["Modelle", "Messen", "eBay", "Einstellungen"]) {
      expect(screen.queryByRole("link", { name: hidden })).not.toBeInTheDocument();
    }
    expect(linkNames(bar)).toEqual(["Bestellungen", "Scannen", "Lager"]);
    await user.click(within(bar).getByRole("button", { name: "Mehr" }));
    expect(linkNames(screen.getByRole("dialog", { name: "Mehr" }))).toEqual(["Übersicht", "Fertigung"]);
  });

  it("counts beside Bestellungen the pieces paid orders wait for, for owner and staff", async () => {
    const { header, bar } = await openShell("owner", "/admin", 3);

    expect(await within(header).findByRole("link", { name: "Bestellungen, 3 Stücke zu fertigen" })).toHaveAttribute(
      "href",
      "/admin/bestellungen",
    );
    expect(within(bar).getByRole("link", { name: /^Bestellungen, 3 Stücke zu fertigen/ })).toBeInTheDocument();
  });

  it("asks nothing about making for a packer", async () => {
    await openShell("packer", "/admin", 3);

    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/stock/to-make"))).toBe(false);
  });

  it("shows owner and staff Modelle first and lights up Einstellungen on the categories", async () => {
    const { header } = await openShell("staff", "/admin/einstellungen/kategorien");

    expect(linkNames(header)).toEqual(["Modelle", "Bestellungen", "Lager", "Fertigung", "Messen", "eBay", "Einstellungen"]);
    expect(within(header).getByRole("link", { name: "Einstellungen" })).toHaveAttribute("aria-current", "page");
    expect(within(header).getByRole("link", { name: "Modelle" })).not.toHaveAttribute("aria-current");
  });

  it("puts the day's work on the phone bar, Scannen in the middle, the rest behind Mehr", async () => {
    const user = userEvent.setup();
    const { bar } = await openShell("owner", "/admin/modelle/neu");

    expect(linkNames(bar)).toEqual(["Modelle", "Bestellungen", "Scannen", "Lager"]);
    // The wizard belongs to Modelle.
    expect(within(bar).getByRole("link", { name: "Modelle" })).toHaveAttribute("aria-current", "page");
    await user.click(within(bar).getByRole("button", { name: "Mehr" }));

    const sheet = screen.getByRole("dialog", { name: "Mehr" });
    expect(linkNames(sheet)).toEqual(["Übersicht", "Fertigung", "Messen", "eBay", "Einstellungen"]);
    expect(within(sheet).getByRole("link", { name: "Einstellungen" })).toHaveAttribute("href", "/admin/einstellungen");

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Mehr" })).not.toBeInTheDocument();
  });
});
