import { describe, expect, it } from "vitest";

import type { PickItemOut } from "@/lib/api/generated/model";

import { nextAction } from "./next-action";

const item = (title: string, state: PickItemOut["state"]) => ({ title, state }) as unknown as PickItemOut;
const list = (items: PickItemOut[], picked = 0, allocated = true) => ({
  allocated,
  complete: picked === items.length,
  items,
  picked,
  total: items.length,
});

describe("nextAction", () => {
  it("asks owner and staff to check an announced transfer", () => {
    const action = nextAction({ order: { status: "pending_payment", channel: "shop" }, pickList: undefined, awaitingTransfer: true, mayManage: true });
    expect(action).toMatchObject({ tone: "act", title: "Überweisung prüfen", action: { href: "#ueberweisung" } });
  });

  it("lets a packer wait for the payment", () => {
    const action = nextAction({ order: { status: "pending_payment", channel: "shop" }, pickList: undefined, awaitingTransfer: true, mayManage: false });
    expect(action.tone).toBe("wait");
  });

  it("names what the workshop still makes", () => {
    const action = nextAction({
      order: { status: "paid", channel: "shop" },
      pickList: list([item("IFA ADK 70", "reserved"), item("EDK 6", "backordered"), item("EDK 6", "backordered")]),
      awaitingTransfer: false,
      mayManage: true,
    });
    expect(action).toMatchObject({ tone: "wait", title: "Wird gefertigt", action: { href: "/admin/fertigung" } });
    expect(action.text).toContain("EDK 6.");
  });

  it("goes from packing to reporting the dispatch", () => {
    const fresh = nextAction({ order: { status: "paid", channel: "shop" }, pickList: list([item("A", "reserved")]), awaitingTransfer: false, mayManage: false });
    expect(fresh.title).toBe("Packen und versenden");
    const packed = nextAction({ order: { status: "paid", channel: "shop" }, pickList: list([item("A", "picked")], 1), awaitingTransfer: false, mayManage: false });
    expect(packed).toMatchObject({ title: "Versand melden", action: { href: "#versand" } });
  });

  it("offers allocating when nothing is reserved yet", () => {
    const action = nextAction({ order: { status: "paid", channel: "shop" }, pickList: list([], 0, false), awaitingTransfer: false, mayManage: true });
    expect(action.title).toBe("Stücke zuteilen");
  });

  it("has nothing left for shipped and cancelled orders", () => {
    for (const status of ["shipped", "cancelled"] as const) {
      expect(nextAction({ order: { status, channel: "shop" }, pickList: undefined, awaitingTransfer: false, mayManage: true }).tone).toBe("done");
    }
  });
});
