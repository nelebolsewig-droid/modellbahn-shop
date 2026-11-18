import type { Route } from "next";

import type { HallOut, OrderSummaryOut, ToMakeOut } from "@/lib/api/generated/model";
import { jobTitle, plateProgress, plateSummary, sinceText } from "@/lib/manufacturing/hall";

/*
 * "Als Nächstes" on the Stellwerk's start page: everything the day asks for, from the
 * data the page already loads, in one list with one button each. The order is the one
 * a workshop works in: a broken printer first, then plates that are done, then parcels,
 * then printers standing idle with work waiting, then what bezahlte Bestellungen still
 * need, last the money still owed.
 */

export type StepTone = "danger" | "action" | "normal";

export type NextStep = {
  key: string;
  /** What kind of work, as a short word in front ("Drucker", "Paket", …). */
  kind: string;
  title: string;
  detail: string;
  href: Route;
  /** The button: one verb or two ("Packen", "Abnehmen"). */
  action: string;
  tone: StepTone;
};

export type NextStepsInput = {
  /** Paid orders that are complete on the shelves, newest first (as the lane lists them). */
  ready: readonly OrderSummaryOut[];
  /** Orders waiting for their money, newest first. */
  unpaid: readonly OrderSummaryOut[];
  hall: HallOut | undefined;
  /** Null for a packer, who does not plan the making. */
  toMake: readonly ToMakeOut[] | null;
  now: Date;
};

/** Unpaid orders become a step once they have waited this long. */
const UNPAID_AFTER_DAYS = 3;

function days(from: string, now: Date): number {
  return Math.floor((now.getTime() - new Date(from).getTime()) / 86_400_000);
}

function printerHref(id: string): Route {
  return `/admin/fertigung/drucker/${id}` as Route;
}

function orderHref(id: string): Route {
  return `/admin/bestellungen/${id}` as Route;
}

export function nextSteps({ ready, unpaid, hall, toMake, now }: NextStepsInput): NextStep[] {
  const steps: NextStep[] = [];
  const printers = (hall?.printers ?? []).filter((desk) => desk.status !== "retired");

  for (const desk of printers.filter((candidate) => candidate.status === "defective")) {
    steps.push({
      key: `defect-${desk.id}`,
      kind: "Drucker",
      title: `${desk.code} ist defekt`,
      detail: [sinceText(new Date(desk.status_changed_at), now), desk.status_note].filter(Boolean).join(" · "),
      href: printerHref(desk.id),
      action: "Ansehen",
      tone: "danger",
    });
  }

  for (const desk of printers) {
    const job = desk.printing;
    const progress = job ? plateProgress(job, now) : null;
    if (job && progress?.overdue) {
      steps.push({
        key: `off-${job.id}`,
        kind: "Platte",
        title: `${desk.code}: ${jobTitle(job)} ist fertig gedruckt`,
        detail: plateSummary(job, 2),
        href: printerHref(desk.id),
        action: "Abnehmen",
        tone: "action",
      });
    }
  }

  for (const job of hall?.post_processing ?? []) {
    steps.push({
      key: `post-${job.id}`,
      kind: "Platte",
      title: `${jobTitle(job)}: gute Teile melden`,
      detail: `in der Nachbearbeitung · ${plateSummary(job, 2)}`,
      href: "/admin/fertigung" as Route,
      action: "Teile melden",
      tone: "normal",
    });
  }

  // The oldest parcel first.
  for (const order of [...ready].reverse()) {
    steps.push({
      key: `pack-${order.id}`,
      kind: "Paket",
      title: `${order.number} packen`,
      detail: `${order.item_count} Stück · ${order.first_line_title} · ${order.recipient}`,
      href: orderHref(order.id),
      action: "Packen",
      tone: "action",
    });
  }

  for (const desk of printers) {
    if (desk.status === "in_service" && desk.printing === null && desk.queue.length > 0) {
      const waiting = desk.queue.length === 1 ? "1 Platte wartet" : `${desk.queue.length} Platten warten`;
      steps.push({
        key: `start-${desk.id}`,
        kind: "Drucker",
        title: `${desk.code} ist frei`,
        detail: `${waiting} · als Nächstes ${jobTitle(desk.queue[0] ?? { number: 0 })}`,
        href: printerHref(desk.id),
        action: "Platte starten",
        tone: "normal",
      });
    }
  }

  for (const row of toMake ?? []) {
    const orders = row.orders.map((order) => order.number).join(", ");
    steps.push({
      key: `make-${row.variant_id}`,
      kind: "Fertigen",
      title: `${row.quantity} × ${row.model}`,
      detail: `${row.finish} · für ${orders}`,
      href: (row.product_id ? `/admin/modelle/${row.product_id}` : "/admin/bestellungen") as Route,
      action: row.product_id ? "Zum Modell" : "Bestellungen",
      tone: "normal",
    });
  }

  for (const order of [...unpaid].reverse()) {
    const waited = days(order.placed_at, now);
    if (waited >= UNPAID_AFTER_DAYS) {
      steps.push({
        key: `unpaid-${order.id}`,
        kind: "Zahlung",
        title: `${order.number} wartet seit ${waited} Tagen aufs Geld`,
        detail: `${order.recipient} · ${order.first_line_title}`,
        href: orderHref(order.id),
        action: "Ansehen",
        tone: "normal",
      });
    }
  }

  return steps;
}
