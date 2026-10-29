import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PLACEHOLDER_MODEL } from "@/lib/workshop/placeholder-model";

import { ExplosionView } from "./explosion-view";
import { MakingOfTeaser } from "./making-of-teaser";

function stubMotion(reduced: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: reduced && query.includes("reduce"),
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

/** The drawing comes into view at once. */
function stubVisible() {
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      constructor(private readonly callback: (entries: { isIntersecting: boolean }[]) => void) {}
      observe() {
        this.callback([{ isIntersecting: true }]);
      }
      disconnect() {}
    },
  );
}

describe("ExplosionView", () => {
  beforeEach(() => stubMotion(false));

  it("lists every position with its print time and the sum", () => {
    render(<ExplosionView model={PLACEHOLDER_MODEL} />);
    // The list stands beside the drawing on wide screens and below it on phones.
    const [table] = screen.getAllByRole("table");
    const rows = within(table!).getAllByRole("row");
    expect(rows).toHaveLength(1 + 12 + 1);
    expect(rows[1]).toHaveTextContent("1Fahrgestellrahmen12 h 40");
    expect(rows.at(-1)).toHaveTextContent("Summe2326 h 40");
  });

  it("says that the model is a placeholder with example values", () => {
    render(<ExplosionView model={PLACEHOLDER_MODEL} />);
    expect(screen.getAllByText(/Teile und Zeiten sind Beispielwerte/)[0]).toBeInTheDocument();
    expect(screen.getByText(`${PLACEHOLDER_MODEL.name}, Platzhalter`)).toBeInTheDocument();
  });

  it("lets the slider take the model apart by hand", () => {
    render(<ExplosionView model={PLACEHOLDER_MODEL} />);
    const slider = screen.getByRole("slider", { name: "Zerlegt" });
    fireEvent.change(slider, { target: { value: "60" } });
    expect(screen.getByText("60 %")).toBeInTheDocument();
  });

  it("lights up the row under the pointer", () => {
    render(<ExplosionView model={PLACEHOLDER_MODEL} />);
    const [table] = screen.getAllByRole("table");
    const row = within(table!).getByRole("row", { name: /Geräteaufbau/ });
    fireEvent.mouseEnter(row);
    expect(row).toHaveClass("bg-accent-subtle");
    fireEvent.mouseLeave(row);
    expect(row).not.toHaveClass("bg-accent-subtle");
  });

  it("falls back to the parts list where the browser has no WebGL", async () => {
    stubVisible();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
    render(<ExplosionView model={PLACEHOLDER_MODEL} />);
    expect(
      await screen.findByText(
        "Die 3D-Ansicht braucht WebGL. Die Stückliste zeigt alle Teile.",
        {},
        { timeout: 10_000 },
      ),
    ).toBeInTheDocument();
  });

  it("stands still, taken apart, for visitors who asked for less motion", () => {
    stubMotion(true);
    render(<ExplosionView model={PLACEHOLDER_MODEL} />);
    expect(screen.getByText("100 %")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Drehung anhalten" })).toBeNull();
  });
});

describe("MakingOfTeaser", () => {
  it("leads to the drawing and keeps a placeholder's figures off the start page", () => {
    render(<MakingOfTeaser />);
    expect(screen.getByRole("link", { name: "Zur Explosionszeichnung" })).toHaveAttribute(
      "href",
      "/so-entsteht-ein-modell",
    );
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
    expect(screen.queryByText("Stunden Druck")).toBeNull();
  });
});
