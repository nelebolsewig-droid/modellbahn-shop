"use client";

import { useQuery } from "@tanstack/react-query";
import type { Route } from "next";
import Link from "next/link";
import { useState, type ReactNode } from "react";

import { nextSteps, type NextStep } from "@/lib/admin/next-steps";

import { Button } from "@/components/ui/button";
import { PendingNotice } from "@/components/ui/pending-notice";
import { listProducts } from "@/lib/api/generated/admin-catalog/admin-catalog";
import { useListProductStock, useListToMake } from "@/lib/api/generated/admin-inventory/admin-inventory";
import { listAdminFairs } from "@/lib/api/generated/admin-site/admin-site";
import type {
  AdminFairOut,
  OrderSummaryOut,
  PrinterDeskOut,
  ProductListItemOut,
  StaffOut,
  ToMakeOut,
} from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";
import { formatProductNumber } from "@/lib/catalog/format";
import { formatWeekdayDate, greetingFor } from "@/lib/format";
import { errorMessage } from "@/lib/i18n/problems";
import { DESK_LAMPS, deskState, formatMinutes, plateProgress, plateSummary, sinceText } from "@/lib/manufacturing/hall";
import { daysBetween, todayInGermany } from "@/lib/site/fairs";
import { OFFICE_ROLES } from "@/lib/staff";
import { cn } from "@/lib/utils";

import { AdminShell } from "./admin-shell";
import { withoutStock } from "./catalog/product-list";
import { ADMIN_PRODUCTS_KEY } from "./catalog/use-product";
import { EventFeed } from "./event-feed";
import { useHall, useNow } from "./manufacturing/use-manufacturing";
import { laneCount, orderAge, splitPaid, useOrderLane } from "./sales/use-order-lanes";
import { FAIRS_KEY } from "./site/fairs-manager";
import { SystemStatus } from "./system-status";

/** The admin start page ("Heute", the Fahrpult of ADR 0030). */
export function Stellwerk() {
  return <AdminShell>{({ staff, revalidate }) => <Today staff={staff} onStreamClosed={revalidate} />}</AdminShell>;
}

type TileKey = "ship" | "make" | "unpaid" | "empty";

/** The corner cut off the tiles, like a type plate. */
const CUT = "[clip-path:polygon(0_0,calc(100%_-_1.375rem)_0,100%_1.375rem,100%_100%,0_100%)]";

/** Models in the shop, page by page; a shop with more pages than this is not expected. */
const MODEL_PAGE = 100;
const MODEL_PAGES_MAX = 20;

async function activeModels(signal?: AbortSignal): Promise<ProductListItemOut[]> {
  const models: ProductListItemOut[] = [];
  let cursor: string | null = null;
  for (let page = 0; page < MODEL_PAGES_MAX; page += 1) {
    const result = await listProducts({ status: "active", limit: MODEL_PAGE, ...(cursor !== null && { cursor }) }, { signal });
    models.push(...result.items);
    cursor = result.next_cursor;
    if (cursor === null) {
      break;
    }
  }
  return models;
}

/**
 * Heute: what the day asks for, as four counts (to pack, to make, unpaid, models with an
 * empty shelf). A tap on a count lists what is behind it. Beside it the printers and the
 * next fair, below it the live feed. A packer sees the counts a packer can act on.
 */
function Today({ staff, onStreamClosed }: { staff: StaffOut; onStreamClosed: () => void }) {
  const office = OFFICE_ROLES.has(staff.role);
  const now = useNow(60_000);
  const [chosen, setChosen] = useState<TileKey | null>(null);

  const paid = useOrderLane("paid");
  const unpaid = useOrderLane("pending_payment");
  const toMake = useListToMake({ query: { enabled: office, refetchInterval: 60_000 } });
  const models = useQuery<ProductListItemOut[], ApiProblem>({
    queryKey: [...ADMIN_PRODUCTS_KEY, "all-active"],
    queryFn: ({ signal }) => activeModels(signal),
    enabled: office,
    staleTime: 5 * 60_000,
  });
  const stock = useListProductStock({
    query: { enabled: office, select: (data) => new Map(data.items.map((line) => [line.product_id, line])) },
  });

  const waiting = new Set((toMake.data?.items ?? []).flatMap((row) => row.orders.map((order) => order.order_id)));
  const { ready } = splitPaid(paid.data?.items ?? [], waiting);
  const empty = models.data && stock.data ? models.data.filter((item) => withoutStock(item, stock.data)) : undefined;
  const hall = useHall();
  const steps = nextSteps({
    ready,
    unpaid: unpaid.data?.items ?? [],
    hall: hall.data,
    toMake: office ? (toMake.data?.items ?? []) : null,
    now,
  });
  const stepsLoading = paid.isPending || hall.isPending || (office && toMake.isPending);

  const tiles: { key: TileKey; label: string; count: string; hint: string }[] = [
    {
      key: "ship",
      label: "Zu versenden",
      count: laneCount(paid.data, ready.length),
      hint: office ? "bezahlt und vollständig im Regal" : "bezahlt, wartet aufs Packen",
    },
    ...(office
      ? [
          {
            key: "make" as const,
            label: "Zu fertigen",
            count: toMake.data ? String(toMake.data.quantity) : "–",
            hint: "Stücke, auf die Bestellungen warten",
          },
        ]
      : []),
    {
      key: "unpaid",
      label: "Zahlung offen",
      count: laneCount(unpaid.data),
      hint: oldestHint(unpaid.data?.items ?? [], now),
    },
    ...(office
      ? [
          {
            key: "empty" as const,
            label: "Ohne Bestand",
            count: empty ? String(empty.length) : "–",
            hint: "Modelle im Shop, von denen nichts im Regal liegt",
          },
        ]
      : []),
  ];

  // Until someone picks a count, the first one with work in it is open (and lit).
  const selected = chosen ?? tiles.find((tile) => tile.count !== "–" && tile.count !== "0")?.key ?? "ship";

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div className="min-w-0">
          <p className="label-caps text-ink-secondary">{formatWeekdayDate(now)}</p>
          <h1 className="mt-3 text-title break-words sm:text-display xl:text-[4rem] xl:leading-none">
            {greetingFor(now)}, {staff.display_name}.
          </h1>
          <p className="mt-3 text-[1.125rem] text-ink-secondary">{dayLine(stepsLoading ? null : steps.length, ready.length)}</p>
        </div>
        <div className="flex flex-wrap gap-2.5">
          {office ? (
            <Button asChild variant="secondary" size="sm" className="border-ink">
              <Link href="/admin/modelle/neu">Neues Modell</Link>
            </Button>
          ) : null}
          <Button asChild size="sm">
            <Link href="/admin/bestellungen">Bestellung suchen</Link>
          </Button>
        </div>
      </div>

      <NextSteps steps={steps} loading={stepsLoading} />

      <div
        role="group"
        aria-label="Was heute ansteht"
        className={cn("mt-8 grid grid-cols-2 gap-3 sm:gap-4", office ? "xl:grid-cols-[1.25fr_1fr_1fr_1fr]" : "xl:max-w-3xl")}
      >
        {tiles.map((tile) => (
          <button
            key={tile.key}
            type="button"
            aria-pressed={tile.key === selected}
            onClick={() => setChosen(tile.key)}
            className={cn(
              CUT,
              "flex min-h-[6.5rem] cursor-pointer flex-col justify-between gap-2 px-4 pt-3.5 pb-3 sm:min-h-[7.5rem] sm:px-5 sm:pt-4 sm:pb-3.5 text-left text-ink transition-[background-color,transform] duration-200 ease-out hover:-translate-y-1 motion-reduce:transition-none motion-reduce:hover:translate-y-0",
              tile.key === selected ? "bg-action" : "bg-surface hover:bg-sunken",
            )}
          >
            <span className="label-caps">{tile.label}</span>
            <span className="font-display text-[2.5rem] leading-[0.8] sm:text-[3.25rem] font-extrabold tracking-[-0.05em] tabular-nums">
              {tile.count}
            </span>
            <span className="text-small">{tile.hint}</span>
          </button>
        ))}
      </div>

      <div className="mt-7 grid items-start gap-6 xl:grid-cols-[1.6fr_1fr]">
        <section aria-live="polite" className="bg-surface px-5 pt-5 pb-2 sm:px-6">
          {selected === "ship" ? (
            <TaskList title="Heute zu versenden" note="älteste zuerst" query={paid} empty="Gerade muss nichts raus.">
              {[...ready].reverse().map((order) => (
                <OrderTask key={order.id} order={order} now={now} action="Packen" primary />
              ))}
            </TaskList>
          ) : selected === "make" ? (
            <TaskList
              title="Zu fertigen"
              note="am längsten wartend zuerst"
              query={toMake}
              empty="Gerade nichts zu fertigen: Jede bezahlte Bestellung hat ihre Stücke."
            >
              {(toMake.data?.items ?? []).map((row) => (
                <MakeTask key={row.variant_id} row={row} />
              ))}
            </TaskList>
          ) : selected === "unpaid" ? (
            <TaskList title="Zahlung offen" note="älteste zuerst" query={unpaid} empty="Keine Bestellung wartet auf ihr Geld.">
              {[...(unpaid.data?.items ?? [])].reverse().map((order) => (
                <OrderTask key={order.id} order={order} now={now} action="Ansehen" />
              ))}
            </TaskList>
          ) : (
            <TaskList
              title="Ohne Bestand"
              note="wird auf Bestellung gefertigt"
              query={models.isError ? models : stock.isError ? stock : models.isPending ? models : stock}
              empty="Von jedem Modell im Shop liegt etwas im Regal."
            >
              {(empty ?? []).map((item) => (
                <Task
                  key={item.id}
                  lead={item.scale_codes.join(" ")}
                  title={item.name}
                  sub={formatProductNumber(item.number)}
                  href={`/admin/modelle/${item.id}` as Route}
                  action="Öffnen"
                />
              ))}
            </TaskList>
          )}
        </section>

        <div className="grid gap-4">
          <HallGlance now={now} />
          {office ? <NextFair /> : null}
        </div>
      </div>

      <div className="mt-10 grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        {/* The browser gave up on the live feed. If the session has ended,
            re-checking it sends the page to the login; otherwise the feed retries. */}
        <EventFeed onStreamClosed={onStreamClosed} />
        <SystemStatus />
      </div>
    </>
  );
}

/** The sentence under the greeting: how much is to do, and how many parcels wait. */
function dayLine(steps: number | null, ready: number): string {
  if (steps === null) {
    return "Das Stellwerk sieht nach, was ansteht …";
  }
  if (steps === 0) {
    return "Gerade ist nichts zu tun. Der Rest läuft.";
  }
  const todo = steps === 1 ? "Eine Sache ist dran" : `${steps} Sachen sind dran`;
  if (ready === 0) {
    return `${todo}, kein Paket muss raus.`;
  }
  return `${todo}, ${ready === 1 ? "ein Paket" : `${ready} Pakete`} davon für den Versand.`;
}

/** Shown at first; the rest folds out. */
const STEPS_SHOWN = 6;

/**
 * "Als Nächstes": the day's work in the order a workshop does it, one button each. The
 * first step is the one to do now and gets the orange button.
 */
function NextSteps({ steps, loading }: { steps: readonly NextStep[]; loading: boolean }) {
  const [all, setAll] = useState(false);
  const shown = all ? steps : steps.slice(0, STEPS_SHOWN);
  return (
    <section aria-labelledby="als-naechstes" className="mt-8 border-[1.5px] border-ink bg-surface px-5 pt-5 pb-3 sm:px-6">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 id="als-naechstes" className="text-heading">
          Als Nächstes
        </h2>
        {steps.length > 0 ? (
          <span className="label-caps text-ink-secondary">
            {steps.length === 1 ? "1 Aufgabe" : `${steps.length} Aufgaben`}
          </span>
        ) : null}
      </div>
      {loading ? (
        <PendingNotice className="py-6">Wird geladen …</PendingNotice>
      ) : steps.length === 0 ? (
        <p className="mt-4 border-t border-line py-6 text-ink-secondary">
          Alles erledigt: Keine Platte wartet, kein Paket muss raus, jede Bestellung hat ihre Stücke.
        </p>
      ) : (
        <ol className="mt-3">
          {shown.map((step, index) => (
            <li
              key={step.key}
              className="grid grid-cols-[2rem_minmax(0,1fr)] items-center gap-x-3 gap-y-2 border-t border-line py-3 sm:grid-cols-[2rem_6rem_minmax(0,1fr)_auto]"
            >
              <span className="font-mono text-hint text-ink-secondary tabular-nums">{String(index + 1).padStart(2, "0")}</span>
              <span
                className={cn(
                  "label-caps max-sm:hidden",
                  step.tone === "danger" ? "text-danger" : step.tone === "action" ? "text-accent" : "text-ink-secondary",
                )}
              >
                {step.kind}
              </span>
              <span className="min-w-0">
                <span className={cn("block font-semibold break-words", step.tone === "danger" && "text-danger")}>
                  {step.title}
                </span>
                {step.detail ? <span className="block truncate text-small text-ink-secondary">{step.detail}</span> : null}
              </span>
              <Button
                asChild
                size="sm"
                variant={index === 0 ? "primary" : "secondary"}
                className={cn("max-sm:col-start-2 max-sm:justify-self-start", index !== 0 && "border-ink")}
              >
                <Link href={step.href}>{step.action}</Link>
              </Button>
            </li>
          ))}
        </ol>
      )}
      {steps.length > STEPS_SHOWN ? (
        <button
          type="button"
          onClick={() => setAll(!all)}
          aria-expanded={all}
          className="mb-1 cursor-pointer border-t border-line pt-3 pb-1 text-small font-semibold text-accent hover:underline hover:underline-offset-4"
        >
          {all ? "Weniger zeigen" : `${steps.length - STEPS_SHOWN} weitere zeigen`}
        </button>
      ) : null}
    </section>
  );
}

/** Orders come newest first, so the last one waits the longest. */
function oldestHint(orders: readonly OrderSummaryOut[], now: Date): string {
  const oldest = orders.at(-1);
  return oldest ? `Vorkasse, älteste ${orderAge(oldest.placed_at, now).long}` : "niemand schuldet etwas";
}

type Loadable = { isPending: boolean; isError: boolean; error: unknown; fetchStatus?: string };

function TaskList({
  title,
  note,
  query,
  empty,
  children,
}: {
  title: string;
  note: string;
  query: Loadable;
  empty: string;
  children: ReactNode[];
}) {
  return (
    <>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 className="text-heading">{title}</h2>
        <span className="label-caps text-ink-secondary">{note}</span>
      </div>
      {query.isError ? (
        <p role="alert" className="py-6 text-small text-danger">
          {errorMessage(query.error)}
        </p>
      ) : query.isPending ? (
        <PendingNotice className="py-6">Wird geladen …</PendingNotice>
      ) : children.length === 0 ? (
        <p className="mt-4 border-t border-line py-8 text-ink-secondary">{empty}</p>
      ) : (
        <ol className="mt-4">{children}</ol>
      )}
    </>
  );
}

function Task({
  lead,
  title,
  sub,
  href,
  action,
  primary = false,
}: {
  lead: ReactNode;
  title: ReactNode;
  sub: ReactNode;
  href: Route;
  action: string;
  primary?: boolean;
}) {
  return (
    <li className="grid grid-cols-[3.25rem_minmax(0,1fr)] items-center gap-x-4 gap-y-2 border-t border-line py-3.5 sm:grid-cols-[3.25rem_minmax(0,1fr)_auto]">
      <span className="font-mono text-hint text-ink-secondary tabular-nums">{lead}</span>
      <span className="min-w-0">
        <span className="block truncate font-semibold">{title}</span>
        <span className="block truncate text-small text-ink-secondary">{sub}</span>
      </span>
      <Button
        asChild
        size="sm"
        variant={primary ? "primary" : "secondary"}
        className={cn("max-sm:col-start-2 max-sm:justify-self-start", !primary && "border-ink")}
      >
        <Link href={href}>{action}</Link>
      </Button>
    </li>
  );
}

function OrderTask({ order, now, action, primary }: { order: OrderSummaryOut; now: Date; action: string; primary?: boolean }) {
  const age = orderAge(order.placed_at, now);
  return (
    <Task
      lead={
        <time dateTime={order.placed_at} title={age.long}>
          {age.short}
        </time>
      }
      title={
        <>
          <span className="font-mono">{order.number}</span> · {order.first_line_title}
        </>
      }
      sub={`${order.item_count} Stück · ${order.recipient} · ${order.channel === "ebay" ? "eBay" : "Shop"}`}
      href={`/admin/bestellungen/${order.id}` as Route}
      action={action}
      primary={primary ?? false}
    />
  );
}

function MakeTask({ row }: { row: ToMakeOut }) {
  return (
    <Task
      lead={`${row.quantity} ×`}
      title={row.model}
      sub={`${row.finish} · für ${row.orders.map((order) => order.number).join(", ")}`}
      href={(row.product_id ? `/admin/modelle/${row.product_id}` : "/admin/bestellungen") as Route}
      action={row.product_id ? "Zum Modell" : "Bestellungen"}
    />
  );
}

/** The printers at a glance: what each one does and how far its plate is. */
function HallGlance({ now }: { now: Date }) {
  const hall = useHall();
  const printers = (hall.data?.printers ?? []).filter((desk) => desk.status !== "retired");
  return (
    <section className="bg-surface px-5 py-5 sm:px-6">
      <div className="flex items-baseline justify-between gap-4">
        <h2 className="text-heading">Druckerhalle</h2>
        <Link href="/admin/fertigung" className="text-small font-semibold text-accent hover:underline hover:underline-offset-4">
          Öffnen
        </Link>
      </div>
      {hall.isPending ? (
        <PendingNotice className="mt-4">Wird geladen …</PendingNotice>
      ) : hall.isError ? (
        <p role="alert" className="mt-4 text-small text-danger">
          {errorMessage(hall.error)}
        </p>
      ) : printers.length === 0 ? (
        <p className="mt-4 text-small text-ink-secondary">Noch kein Drucker eingerichtet.</p>
      ) : (
        <ul className="mt-1">
          {printers.map((desk) => (
            <PrinterLine key={desk.id} desk={desk} now={now} />
          ))}
        </ul>
      )}
    </section>
  );
}

function PrinterLine({ desk, now }: { desk: PrinterDeskOut; now: Date }) {
  const state = deskState(desk);
  const progress = desk.printing ? plateProgress(desk.printing, now) : null;
  const down = state === "defective" || state === "in_repair";
  const what = desk.printing ? plateSummary(desk.printing, 1) || DESK_LAMPS[state].label : DESK_LAMPS[state].label;
  const rest = desk.printing
    ? progress === null
      ? "läuft"
      : progress.overdue
        ? "sollte fertig sein"
        : `noch ${formatMinutes(progress.remainingMinutes)}`
    : down
      ? sinceText(new Date(desk.status_changed_at), now)
      : desk.queue.length > 0
        ? `${desk.queue.length} in der Warteschlange`
        : "bereit";
  return (
    <li className="mt-4">
      <div className="flex justify-between gap-3 text-small">
        <span className="min-w-0 truncate">
          <b className="font-mono font-medium">{desk.code}</b> · {what}
        </span>
        <span className="shrink-0 font-mono text-hint text-ink-secondary tabular-nums">{rest}</span>
      </div>
      <div aria-hidden="true" className="mt-1.5 h-2.5 bg-sunken">
        <div
          className={cn(
            "h-full",
            desk.printing ? "bg-action" : down ? "stellwerk-hatch" : "bg-success",
            state === "defective" && "text-danger",
          )}
          style={{ width: desk.printing ? `${Math.round((progress?.fraction ?? 0.04) * 100)}%` : "100%" }}
        />
      </div>
    </li>
  );
}

/** The next fair on the calendar, with the days until it opens. */
function NextFair() {
  const fairs = useQuery<AdminFairOut[], ApiProblem>({
    queryKey: FAIRS_KEY,
    queryFn: async ({ signal }) => (await listAdminFairs({ signal })).items,
  });
  const today = todayInGermany();
  const next = (fairs.data ?? [])
    .filter((fair) => fair.ends_on >= today)
    .sort((a, b) => a.starts_on.localeCompare(b.starts_on))[0];
  if (!fairs.isSuccess) {
    return null;
  }
  return (
    <section className="flex flex-wrap items-center justify-between gap-4 border-[1.5px] border-ink px-5 py-4 sm:px-6">
      <div className="min-w-0">
        <h2 className="label-caps font-normal text-ink-secondary">Nächste Messe</h2>
        <p className="mt-1 text-[1.0625rem] font-semibold">
          {next ? `${next.name} · ${untilText(next.starts_on, today)}` : "Keine Messe im Kalender"}
        </p>
        {next ? <p className="text-small text-ink-secondary">{[next.when, next.city].filter(Boolean).join(" · ")}</p> : null}
      </div>
      <Link href="/admin/messen" className="font-semibold text-accent hover:underline hover:underline-offset-4">
        {next ? "Zur Messe" : "Messe eintragen"}
      </Link>
    </section>
  );
}

/** "in 23 Tagen", "morgen", "läuft gerade"; both dates as YYYY-MM-DD. */
function untilText(startsOn: string, today: string): string {
  const days = daysBetween(today, startsOn);
  if (days <= 0) {
    return days === 0 ? "heute" : "läuft gerade";
  }
  return days === 1 ? "morgen" : `in ${days} Tagen`;
}
