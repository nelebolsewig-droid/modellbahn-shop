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

async function openShell(role: StaffRole, pathname: string) {
  navigation.pathname = pathname;
  routeFetch(fetchMock, { "GET /api/v1/admin/auth/me": () => jsonResponse(staff(role)) });
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
  it("shows a packer only Übersicht, Bestellungen, Lager, Fertigung and Scannen", async () => {
    const { header, bar } = await openShell("packer", "/admin/lager");

    expect(linkNames(header)).toEqual(["Übersicht", "Bestellungen", "Lager", "Fertigung"]);
    expect(within(header).getByRole("link", { name: "Lager" })).toHaveAttribute("aria-current", "page");
    expect(screen.getAllByRole("link", { name: "Scannen" })[0]).toHaveAttribute("href", "/admin/scanner");
    for (const hidden of ["Katalog", "Messen", "eBay", "Einstellungen", "Neues Modell"]) {
      expect(screen.queryByRole("link", { name: hidden })).not.toBeInTheDocument();
    }
    // On the phone a single remaining entry needs no "Mehr".
    expect(linkNames(bar)).toEqual(["Übersicht", "Bestellungen", "Scannen", "Lager", "Fertigung"]);
    expect(within(bar).queryByRole("button", { name: "Mehr" })).not.toBeInTheDocument();
  });

  it("shows owner and staff every entry and lights up Einstellungen on the categories", async () => {
    const { header } = await openShell("staff", "/admin/katalog/kategorien");

    expect(linkNames(header)).toEqual([
      "Übersicht",
      "Bestellungen",
      "Lager",
      "Fertigung",
      "Katalog",
      "Messen",
      "eBay",
      "Einstellungen",
    ]);
    expect(within(header).getByRole("link", { name: "Einstellungen" })).toHaveAttribute("aria-current", "page");
    expect(within(header).getByRole("link", { name: "Katalog" })).not.toHaveAttribute("aria-current");
  });

  it("puts Scannen in the middle of the phone bar and the rest behind Mehr", async () => {
    const user = userEvent.setup();
    const { bar } = await openShell("owner", "/admin/erfassen");

    expect(linkNames(bar)).toEqual(["Übersicht", "Bestellungen", "Scannen", "Lager"]);
    await user.click(within(bar).getByRole("button", { name: "Mehr" }));

    const sheet = screen.getByRole("dialog", { name: "Mehr" });
    expect(linkNames(sheet)).toEqual(["Fertigung", "Katalog", "Neues Modell", "Messen", "eBay", "Einstellungen"]);
    expect(within(sheet).getByRole("link", { name: "Neues Modell" })).toHaveAttribute("href", "/admin/erfassen");
    expect(within(sheet).getByRole("link", { name: "Neues Modell" })).toHaveAttribute("aria-current", "page");
    expect(within(sheet).getByRole("link", { name: "Einstellungen" })).toHaveAttribute("href", "/admin/einstellungen");

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Mehr" })).not.toBeInTheDocument();
  });
});
