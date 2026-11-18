import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { OrderOut } from "@/lib/api/generated/model";

import { WorkshopTicker } from "./workshop-ticker";

const order = (patch: Partial<OrderOut>) =>
  ({ status: "paid", lead_time_min_weeks: 2, lead_time_max_weeks: 4, making_started_at: null, ...patch }) as OrderOut;

describe("WorkshopTicker", () => {
  it("says the plates are planned before the printer starts", () => {
    render(<WorkshopTicker order={order({})} />);
    expect(screen.getByText(/stehen auf dem Druckplan/)).toBeInTheDocument();
    expect(screen.getByText("Eingeplant").closest("li")).toHaveAttribute("aria-current", "step");
  });

  it("says since when the printer runs", () => {
    render(<WorkshopTicker order={order({ making_started_at: "2026-11-18T09:30:00Z" })} />);
    expect(screen.getByText(/läuft der Drucker für dich/)).toBeInTheDocument();
    expect(screen.getByText("Im Drucker").closest("li")).toHaveAttribute("aria-current", "step");
  });

  it("stays away from orders shipped from the shelves", () => {
    const { container } = render(<WorkshopTicker order={order({ lead_time_min_weeks: null })} />);
    expect(container).toBeEmptyDOMElement();
  });
});
