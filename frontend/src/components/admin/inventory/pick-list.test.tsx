import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { PickItemOut, PickListOut } from "@/lib/api/generated/model";

import { PickList, pickRows, splitTitle } from "./pick-list";

function piece(position: number, state: PickItemOut["state"], variant = "v1", place = "R01-B02"): PickItemOut {
  const waiting = state === "backordered";
  return {
    allocation_id: `a${position}`,
    order_line_id: `l-${variant}`,
    piece: position,
    position,
    sku: variant === "v1" ? "MB-000006-H0-B" : "MB-000006-H0-F-ROT",
    title: variant === "v1" ? "Stellwerk Altenau · H0 · Bausatz" : "Stellwerk Altenau · H0 · Fertigmodell, Rot",
    variant_id: variant,
    state,
    unit_code: waiting ? null : `J4WZXRT2S${position}`,
    location: waiting
      ? null
      : { id: place, code: place, name: "Boden 2", kind: "compartment", depth: 2, holds_goods: true, parent_id: null, path: "L.R01.B02" },
    place: waiting ? null : "Regal 1, Boden 2",
  };
}

function list(items: PickItemOut[]): PickListOut {
  return {
    order_id: "o1",
    order_number: "MB-2026-00042",
    order_status: "paid",
    ship_recipient: "Erika Mustermann",
    allocated: true,
    items,
    picked: 0,
    total: items.length,
    complete: false,
  };
}

describe("PickList", () => {
  it("names model, Ausführung and place, never the code of a piece", () => {
    render(<PickList list={list([piece(1, "reserved"), piece(2, "reserved"), piece(3, "reserved", "v2"), piece(4, "backordered", "v2")])} />);

    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent("Regal 1, Boden 2");
    expect(rows[0]).toHaveTextContent("Als Nächstes2 × Stellwerk Altenau");
    expect(rows[0]).toHaveTextContent("H0 · Bausatz · MB-000006-H0-B");
    expect(rows[1]).toHaveTextContent("H0 · Fertigmodell, Rot");
    expect(rows[2]).toHaveTextContent("Fertigung");
    expect(screen.queryByText(/J4WZ/)).toBeNull();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("splits the frozen title of an order line into model and Ausführung", () => {
    expect(splitTitle("Stellwerk Altenau · H0 · Fertigmodell, Rot")).toEqual({ model: "Stellwerk Altenau", finish: "H0 · Fertigmodell, Rot" });
    expect(splitTitle("Bahnhof · Nord · H0 · Bausatz")).toEqual({ model: "Bahnhof · Nord", finish: "H0 · Bausatz" });
    expect(splitTitle("Gelöscht")).toEqual({ model: "Gelöscht", finish: "" });
  });

  it("puts pieces together only when Ausführung, place and state agree", () => {
    const rows = pickRows([piece(1, "reserved"), piece(2, "reserved", "v1", "R02"), piece(3, "picked"), piece(4, "picked")]);
    expect(rows.map((row) => row.map((item) => item.allocation_id))).toEqual([["a1"], ["a2"], ["a3", "a4"]]);
  });
});
