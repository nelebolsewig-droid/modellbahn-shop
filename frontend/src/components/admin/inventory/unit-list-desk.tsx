"use client";

import type { Route } from "next";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { ConnectionLamp } from "@/components/admin/connection-lamp";
import { Panel } from "@/components/admin/panel";
import { OptionGroup, OptionPill } from "@/components/ui/option-pill";
import { PendingNotice } from "@/components/ui/pending-notice";
import { StatusBadge } from "@/components/ui/status-badge";
import { useListStock, useListUnits } from "@/lib/api/generated/admin-inventory/admin-inventory";
import type { StaffRole, UnitOut, UnitStatus } from "@/lib/api/generated/model";
import { formatShortDate } from "@/lib/format";
import { SCRAP_REASON_LABELS, UNIT_STATUS_LABELS, UNIT_STATUS_TONES } from "@/lib/inventory/labels";
import { pieces, RESTORABLE_STATUSES, SELECTABLE_STATUSES, unitListHref } from "@/lib/inventory/selection";
import { errorMessage } from "@/lib/i18n/problems";
import { ADMIN_EVENTS_URL, INVENTORY_EVENT_TYPES, stockEventOf } from "@/lib/realtime/events";
import { useEventStream } from "@/lib/realtime/use-event-stream";
import { cn } from "@/lib/utils";

import { MAY_MANAGE_STOCK } from "./inventory-overview";
import { useInventoryRefresh } from "./part-dialogs";
import { SelectAllCheckbox, UnitCheckbox, UnitSelectionBar, useUnitSelection, type UnitSelection } from "./unit-selection";

type Counted = "labeled" | "in_stock" | "allocated" | "picked";

type Filter = { key: string; label: string; statuses: UnitStatus[]; counted: Counted[] };

/** The states to look at; `key` is the value of `?zustand=` in the address. */
export const UNIT_FILTERS: readonly Filter[] = [
  { key: "bestand", label: "Im Bestand", statuses: ["labeled", "in_stock", "allocated", "picked"], counted: ["labeled", "in_stock", "allocated", "picked"] },
  { key: "unverbucht", label: "Unverbucht", statuses: ["labeled"], counted: ["labeled"] },
  { key: "lager", label: "Frei im Lager", statuses: ["in_stock"], counted: ["in_stock"] },
  { key: "reserviert", label: "Reserviert", statuses: ["allocated"], counted: ["allocated"] },
  { key: "kommissioniert", label: "Kommissioniert", statuses: ["picked"], counted: ["picked"] },
  { key: "versendet", label: "Versendet", statuses: ["shipped"], counted: [] },
  { key: "ausgebucht", label: "Ausgebucht", statuses: ["scrapped"], counted: [] },
];

const DEFAULT_FILTER = UNIT_FILTERS[0] as Filter;

const NOTHING: ReadonlySet<UnitStatus> = new Set();

/** The list's own word for labelled pieces, as in the stock overview: never put away. */
function statusLabel(status: UnitStatus): string {
  return status === "labeled" ? "Unverbucht" : UNIT_STATUS_LABELS[status];
}

type UnitListDeskProps = {
  variantId: string | null;
  initialFilter: string | null;
  staffRole: StaffRole;
  onStreamClosed: () => void;
};

/**
 * The pieces themselves, one by one: of one article, or every unbooked one in the store.
 * Ticked pieces are stored, moved or taken out of the stock together; this is where a
 * count that is too high is put right.
 */
const REFRESH_DEBOUNCE_MS = 300;

export function UnitListDesk({ variantId, initialFilter, staffRole, onStreamClosed }: UnitListDeskProps) {
  const refresh = useInventoryRefresh();
  // A burst of stock events (a big move books one per piece) refreshes the lists once.
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (refreshTimer.current !== null) {
        clearTimeout(refreshTimer.current);
      }
    },
    [],
  );
  const refreshSoon = () => {
    if (refreshTimer.current !== null) {
      clearTimeout(refreshTimer.current);
    }
    refreshTimer.current = setTimeout(() => {
      refreshTimer.current = null;
      refresh();
    }, REFRESH_DEBOUNCE_MS);
  };
  const [filter, setFilter] = useState<Filter>(UNIT_FILTERS.find((entry) => entry.key === initialFilter) ?? DEFAULT_FILTER);
  const units = useListUnits({ ...(variantId !== null && { variant_id: variantId }), status: filter.statuses });
  const stock = useListStock();
  const lines = (stock.data?.items ?? []).filter((line) => variantId === null || line.variant_id === variantId);
  const article = variantId === null ? null : (lines[0]?.variant ?? units.data?.items[0]?.variant ?? null);
  const items = units.data?.items ?? [];
  const mayManage = MAY_MANAGE_STOCK.has(staffRole);
  // Scrapped pieces are ticked in their own list, to book them in again (owner and staff).
  const restoring = filter.key === "ausgebucht";
  const selection = useUnitSelection(
    items,
    restoring ? (mayManage ? RESTORABLE_STATUSES : NOTHING) : SELECTABLE_STATUSES,
  );
  const stream = useEventStream({
    url: ADMIN_EVENTS_URL,
    eventTypes: INVENTORY_EVENT_TYPES,
    onMessage(data) {
      const event = stockEventOf(data);
      if (event !== null && event.partNumber === null && (variantId === null || event.variantId === null || event.variantId === variantId)) {
        refreshSoon();
      }
    },
    onClosed: onStreamClosed,
  });
  const count = (filterEntry: Filter) =>
    filterEntry.counted.length === 0 || !stock.isSuccess
      ? null
      : lines.reduce((sum, line) => sum + filterEntry.counted.reduce((part, key) => part + line[key], 0), 0);
  const unbooked = count(UNIT_FILTERS[1] as Filter) ?? 0;

  return (
    <>
      <Link href="/admin/lager" className="inline-flex items-center gap-2 text-small font-medium text-ink-secondary hover:text-ink">
        <span aria-hidden="true">←</span> Lager
      </Link>
      <div className="mt-6 flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="label-caps text-ink-tertiary">{variantId === null ? "Alle Modelle" : "Stücke eines Modells"}</p>
          <h1 className="mt-3 text-heading sm:text-title">{variantId === null ? "Stücke" : (article?.title ?? "Gelöschtes Modell")}</h1>
          {article ? (
            <p className="mt-2 flex flex-wrap gap-x-3 font-mono text-hint text-ink-tertiary">
              <span>{article.sku}</span>
              {article.gtin ? <span>EAN {article.gtin}</span> : null}
            </p>
          ) : null}
        </div>
        <ConnectionLamp state={stream.state} onReconnect={stream.reconnect} />
      </div>

      <OptionGroup
        label="Zustand"
        className="mt-6"
        value={filter.key}
        onValueChange={(key) => setFilter(UNIT_FILTERS.find((entry) => entry.key === key) ?? DEFAULT_FILTER)}
      >
        {UNIT_FILTERS.map((entry) => {
          const number = count(entry);
          return (
            <OptionPill key={entry.key} value={entry.key}>
              {entry.label}
              {number !== null ? <span className="tabular-nums opacity-70">{number}</span> : null}
            </OptionPill>
          );
        })}
      </OptionGroup>

      {unbooked > 0 && filter.key !== "unverbucht" ? (
        <div className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded-md border border-warning bg-warning-subtle px-5 py-4 text-small">
          <p>
            <span className="font-medium">{pieces(unbooked)} unverbucht:</span> etikettiert, aber ohne Platz. Shop und eBay
            zählen sie erst, wenn sie in einem Platz liegen.
          </p>
          <button
            type="button"
            onClick={() => setFilter(UNIT_FILTERS[1] as Filter)}
            className="cursor-pointer font-medium text-ink underline underline-offset-2 hover:no-underline"
          >
            Nur unverbuchte zeigen
          </button>
        </div>
      ) : null}
      {filter.key === "unverbucht" && items.length > 0 ? (
        <p className="mt-6 text-small text-ink-secondary">
          Die Stücke ankreuzen, die im Regal liegen, dann „Einlagern …“ und den Platz wählen. Doppelt gedruckte Etiketten
          bucht „Ausbuchen …“ mit dem Grund „Falsch erfasst“ aus.
        </p>
      ) : null}
      {restoring && mayManage && items.length > 0 ? (
        <p className="mt-6 text-small text-ink-secondary">
          Falsch ausgebucht oder doch gefunden? Die Stücke ankreuzen, dann „Wieder einbuchen …“ und den Platz wählen, in dem
          sie liegen.
        </p>
      ) : null}

      <Panel
        title={units.isSuccess ? `${filter.label} · ${pieces(items.length)}` : filter.label}
        code="LG 31"
        className="mt-6"
        actions={items.length > 0 ? <SelectAllCheckbox units={items} selection={selection} /> : null}
      >
        {units.isPending ? <PendingNotice>Die Stücke werden geladen …</PendingNotice> : null}
        {units.isError ? <p className="text-small text-danger">{errorMessage(units.error)}</p> : null}
        {units.isSuccess && items.length === 0 ? <p className="text-small text-ink-secondary">Keine Stücke in diesem Zustand.</p> : null}
        {items.length > 0 ? (
          variantId === null ? (
            <GroupedUnits units={items} selection={selection} />
          ) : (
            <UnitRows units={items} selection={selection} />
          )
        ) : null}
        {units.data?.more ? (
          <p className="mt-4 text-hint text-ink-tertiary">Es sind mehr; gezeigt sind die ältesten 500.</p>
        ) : null}
        <UnitSelectionBar selection={selection} mayScrap={mayManage} />
      </Panel>
    </>
  );
}

/** Every article on its own, with a box to tick all its pieces. */
function GroupedUnits({ units, selection }: { units: readonly UnitOut[]; selection: UnitSelection<UnitOut> }) {
  const groups = new Map<string, UnitOut[]>();
  for (const unit of units) {
    groups.set(unit.variant_id, [...(groups.get(unit.variant_id) ?? []), unit]);
  }
  const ordered = [...groups.values()].sort((a, b) =>
    (a[0]?.variant?.title ?? "").localeCompare(b[0]?.variant?.title ?? "", "de"),
  );
  return (
    <div className="space-y-6">
      {ordered.map((group) => {
        const first = group[0] as UnitOut;
        const title = first.variant?.title ?? "Gelöschtes Modell";
        return (
          <section key={first.variant_id} aria-label={title}>
            <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 pb-2">
              <h3 className="min-w-0 text-small font-medium">
                <Link href={unitListHref({ variantId: first.variant_id })} className="hover:underline">
                  {title}
                </Link>
                <span className="ml-2 font-mono text-hint font-normal text-ink-tertiary">{first.variant?.sku}</span>
              </h3>
              <SelectAllCheckbox
                units={group}
                selection={selection}
                label={
                  <>
                    Alle {group.length}
                    <span className="sr-only"> von {title}</span>
                  </>
                }
              />
            </div>
            <UnitRows units={group} selection={selection} />
          </section>
        );
      })}
    </div>
  );
}

function UnitRows({ units, selection }: { units: readonly UnitOut[]; selection: UnitSelection<UnitOut> }) {
  return (
    <ul className="divide-y divide-line border-y border-line">
      {units.map((unit) => (
        <li
          key={unit.id}
          className={cn(
            "grid grid-cols-[auto_minmax(0,1fr)_auto] items-baseline gap-x-3 gap-y-1 py-2.5",
            unit.status === "labeled" && "-mx-2 bg-warning-subtle/50 px-2",
          )}
        >
          <span className="self-center">
            <UnitCheckbox unit={unit} selection={selection} />
          </span>
          <div className="min-w-0">
            <Link href={`/admin/lager/einheiten/${unit.code}` as Route} className="font-mono text-small font-medium hover:underline">
              {unit.display_code}
            </Link>
            <p className="truncate text-hint text-ink-tertiary">
              Erfasst <time dateTime={unit.created_at}>{formatShortDate(new Date(unit.created_at))}</time>
              {unit.scrap_reason ? ` · ${SCRAP_REASON_LABELS[unit.scrap_reason]}` : ""}
              {unit.scrap_note ? ` · „${unit.scrap_note}“` : ""}
            </p>
          </div>
          <div className="text-right">
            <StatusBadge tone={UNIT_STATUS_TONES[unit.status]}>{statusLabel(unit.status)}</StatusBadge>
            <p className="mt-0.5 font-mono text-hint text-ink-tertiary">
              {unit.location ? (
                <Link href={`/admin/lager/plaetze/${unit.location.code}` as Route} className="hover:underline">
                  {unit.location.code}
                </Link>
              ) : unit.status === "labeled" ? (
                <span className="font-sans text-warning">ohne Platz</span>
              ) : null}
              {unit.order_number ? ` ${unit.order_number}` : ""}
            </p>
          </div>
        </li>
      ))}
    </ul>
  );
}
