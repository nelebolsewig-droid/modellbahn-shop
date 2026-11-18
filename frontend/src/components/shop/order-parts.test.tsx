import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { orderOut } from "@/test/sales";

import { OrderTimeline } from "./order-parts";

describe("OrderTimeline", () => {
  it("shows the making as the station being worked on, with the date it should be done", () => {
    render(
      <OrderTimeline
        order={orderOut({
          status: "paid",
          paid_at: "2026-11-18T12:00:00Z",
          lead_time_min_weeks: 2,
          lead_time_max_weeks: 4,
        })}
      />,
    );
    const stations = screen.getAllByRole("listitem").map((item) => item.textContent);
    expect(stations[2]).toContain("Wird gefertigt");
    expect(stations[2]).toContain("(gerade)");
    expect(stations[2]).toContain("bis ca. 16. Dezember 2026");
    expect(stations[3]).toContain("Versendet");
  });

  it("has no making station when everything came from the shelves", () => {
    render(
      <OrderTimeline
        order={orderOut({
          status: "paid",
          paid_at: "2026-11-18T12:00:00Z",
          lead_time_min_weeks: null,
          lead_time_max_weeks: null,
        })}
      />,
    );
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
    expect(screen.queryByText(/gefertigt/)).not.toBeInTheDocument();
  });

  it("marks the making done once the parcel left", () => {
    render(
      <OrderTimeline
        order={orderOut({
          status: "shipped",
          paid_at: "2026-11-18T12:00:00Z",
          shipped_at: "2026-12-01T09:00:00Z",
          lead_time_min_weeks: 2,
          lead_time_max_weeks: 4,
        })}
      />,
    );
    expect(screen.getByText("Gefertigt")).toBeInTheDocument();
    expect(screen.queryByText("(gerade)")).not.toBeInTheDocument();
  });
});
