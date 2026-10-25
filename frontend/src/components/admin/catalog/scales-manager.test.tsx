import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AdminScaleOut } from "@/lib/api/generated/model";
import { requestsTo, routeFetch } from "@/test/fetch-routes";
import { jsonResponse, problemResponse, renderWithQueryClient } from "@/test/render";

import { ScalesManager } from "./scales-manager";

const fetchMock = vi.fn<typeof fetch>();

function scale(overrides: Partial<AdminScaleOut>): AdminScaleOut {
  return {
    code: "H0",
    name: "H0",
    ratio: "1:87",
    ratio_denominator: 87,
    track_gauge_mm: 16.5,
    product_count: 0,
    ...overrides,
  };
}

const H0 = scale({ product_count: 4 });
const ROAD = scale({ code: "124", name: "1:24", ratio: "1:24", ratio_denominator: 24, track_gauge_mm: null });

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
});

describe("ScalesManager", () => {
  it("lists each scale with ratio, track and use; a used one cannot be deleted", async () => {
    routeFetch(fetchMock, { "GET /api/v1/admin/scales": () => jsonResponse([H0, ROAD]) });
    renderWithQueryClient(<ScalesManager />);

    const rows = await screen.findAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("Gleis 16,5 mm");
    expect(rows[0]).toHaveTextContent("4 Produkte");
    expect(within(rows[0] as HTMLElement).getByRole("button", { name: "Löschen" })).toBeDisabled();
    expect(rows[1]).toHaveTextContent("ohne Gleis");
    expect(within(rows[1] as HTMLElement).getByRole("button", { name: "Löschen" })).toBeEnabled();
  });

  it("adds a scale with a German decimal ratio and shows its metre while typing", async () => {
    const created = scale({ code: "0", name: "0", ratio: "1:43,5", ratio_denominator: 43.5, track_gauge_mm: 32 });
    routeFetch(fetchMock, {
      "GET /api/v1/admin/scales": () => jsonResponse([H0]),
      "POST /api/v1/admin/scales": () => jsonResponse(created, 201),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<ScalesManager />);

    const form = await screen.findByRole("form", { name: "Neuer Maßstab" });
    await user.type(within(form).getByLabelText("Code"), "0");
    await user.type(within(form).getByLabelText("Name"), "0");
    await user.type(within(form).getByLabelText("Verhältnis 1:"), "43,5");
    expect(within(form).getByText("1 m ≙ 23 mm")).toBeInTheDocument();
    await user.type(within(form).getByLabelText("Spurweite in mm"), "32");
    await user.click(within(form).getByRole("button", { name: "Maßstab anlegen" }));

    await waitFor(() => expect(requestsTo(fetchMock, "POST /api/v1/admin/scales")).toHaveLength(1));
    expect(requestsTo(fetchMock, "POST /api/v1/admin/scales")[0]?.body).toEqual({
      code: "0",
      name: "0",
      ratio_denominator: 43.5,
      track_gauge_mm: 32,
    });
  });

  it("changes a scale without touching its code and shows the API's answer at the field", async () => {
    routeFetch(fetchMock, {
      "GET /api/v1/admin/scales": () => jsonResponse([H0, ROAD]),
      "PATCH /api/v1/admin/scales/124": () =>
        problemResponse(422, "validation_failed", [{ field: "name", code: "duplicate", message: "taken" }]),
    });
    const user = userEvent.setup();
    renderWithQueryClient(<ScalesManager />);

    const rows = await screen.findAllByRole("listitem");
    await user.click(within(rows[1] as HTMLElement).getByRole("button", { name: "Bearbeiten" }));
    const form = screen.getByRole("form", { name: "Maßstab 1:24 bearbeiten" });
    expect(within(form).getByLabelText("Code")).toHaveAttribute("readonly");
    const name = within(form).getByLabelText("Name");
    await user.clear(name);
    await user.type(name, "H0");
    await user.click(within(form).getByRole("button", { name: "Speichern" }));

    expect(await within(form).findByText("Diesen Namen trägt schon ein anderer Maßstab.")).toBeInTheDocument();
    expect(requestsTo(fetchMock, "PATCH /api/v1/admin/scales/124")[0]?.body).toEqual({
      name: "H0",
      ratio_denominator: 24,
      track_gauge_mm: null,
    });
  });
});
