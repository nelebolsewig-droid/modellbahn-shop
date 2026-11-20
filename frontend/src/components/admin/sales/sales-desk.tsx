"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { Route } from "next";
import Link from "next/link";
import { useMemo, useState, type ReactNode } from "react";

import { Panel } from "@/components/admin/panel";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { PendingNotice } from "@/components/ui/pending-notice";
import { recordUnitSale } from "@/lib/api/generated/admin-inventory/admin-inventory";
import { getGetSalesReportQueryKey, useGetSalesReport } from "@/lib/api/generated/admin-sales/admin-sales";
import { useListAdminFairs } from "@/lib/api/generated/admin-site/admin-site";
import type { AdminFairOut, ReportChannel, SaleChannel, SoldLineOut, UnitOut } from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";
import { formatPrice } from "@/lib/catalog/format";
import { errorMessage } from "@/lib/i18n/problems";
import {
  addDays,
  byChannel,
  byDay,
  byMonth,
  CHANNEL_LABELS,
  CHANNEL_SWATCHES,
  daysOf,
  longDayLabel,
  monthLabel,
  piecesLabel,
  share,
  shopDay,
  SPAN_LABELS,
  spanFor,
  spanLabel,
  timeLabel,
  totals,
  weekdayLabel,
  type ChannelShare,
  type Span,
  type SpanKey,
  type Tally,
} from "@/lib/sales/report";
import { cn } from "@/lib/utils";

import { SaleFields, saleDraft, saleOf, type SaleDraft } from "./sale-fields";
import { TillPanel } from "./till-panel";

/** The page refreshes itself while it is open: Johann sells, the office watches. */
const REFRESH_MS = 60_000;
const SPAN_KEYS: readonly SpanKey[] = ["today", "yesterday", "week", "month", "thisMonth", "thisYear"];
/** Up to this many days, the course is shown day by day; beyond, month by month. */
const DAILY_UP_TO = 31;

type Choice = { kind: "preset"; key: SpanKey } | { kind: "fair"; fair: AdminFairOut } | { kind: "custom"; span: Span };

function spanOf(choice: Choice): Span {
  if (choice.kind === "preset") {
    return spanFor(choice.key);
  }
  if (choice.kind === "fair") {
    const today = shopDay(new Date());
    return { start: choice.fair.starts_on, end: choice.fair.ends_on < today ? choice.fair.ends_on : today };
  }
  return choice.span;
}

/** The fairs worth a button: running now or over within the last 60 days, the latest first. */
function recentFairs(fairs: readonly AdminFairOut[]): AdminFairOut[] {
  const today = shopDay(new Date());
  const since = addDays(today, -60);
  return fairs
    .filter((fair) => fair.starts_on <= today && fair.ends_on >= since)
    .sort((a, b) => b.starts_on.localeCompare(a.starts_on))
    .slice(0, 3);
}

/**
 * Verkäufe (ADR 0039): everything sold in a span, online and outside, with the money it
 * brought in. Made for the phone at a fair stand as much as for the desk: the figure
 * first, the channels as one bar, the course by day, and every sale with the way to
 * correct a piece's channel and price.
 */
export function SalesDesk() {
  const [choice, setChoice] = useState<Choice>({ kind: "preset", key: "today" });
  const [filter, setFilter] = useState<ReportChannel | "all">("all");
  const span = spanOf(choice);
  const report = useGetSalesReport(span, { query: { refetchInterval: REFRESH_MS, placeholderData: (previous) => previous } });
  const fairs = useListAdminFairs({ query: { select: (list) => recentFairs(list.items) } });

  const all = useMemo(() => report.data?.lines ?? [], [report.data]);
  const lines = useMemo(() => (filter === "all" ? all : all.filter((line) => line.channel === filter)), [all, filter]);
  const channels = useMemo(() => byChannel(all), [all]);

  return (
    <div className="space-y-6">
      <SpanPicker choice={choice} onChoose={setChoice} fairs={fairs.data ?? []} span={span} />

      {report.isError ? <p className="text-small text-danger">{errorMessage(report.error)}</p> : null}
      {report.isPending ? <PendingNotice>Die Verkäufe werden zusammengezählt …</PendingNotice> : null}

      {report.data ? (
        <>
          <ChannelFilter channels={channels} total={all.length} value={filter} onChange={setFilter} />
          <Headline lines={lines} channels={filter === "all" ? channels : byChannel(lines)} span={span} refreshing={report.isFetching} />
          <TillPanel />
          <Course lines={lines} span={span} />
          <SaleList lines={lines} />
        </>
      ) : null}
    </div>
  );
}

/* --- Span ---------------------------------------------------------------------------- */

function Chip({ active, onClick, children, live = false }: { active: boolean; onClick: () => void; children: ReactNode; live?: boolean }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "inline-flex h-10 shrink-0 items-center gap-2 border px-4 text-sm font-medium whitespace-nowrap transition-colors",
        active ? "border-ink bg-ink text-on-selected" : "border-line-control bg-surface text-ink hover:border-ink",
      )}
    >
      {live ? <span aria-hidden="true" className="size-2 animate-lamp-pulse rounded-full bg-action" /> : null}
      {children}
    </button>
  );
}

function SpanPicker({
  choice,
  onChoose,
  fairs,
  span,
}: {
  choice: Choice;
  onChoose: (choice: Choice) => void;
  fairs: readonly AdminFairOut[];
  span: Span;
}) {
  const [from, setFrom] = useState(span.start);
  const [to, setTo] = useState(span.end);
  const today = shopDay(new Date());
  return (
    <section aria-label="Zeitraum">
      {/* One row that scrolls sideways on the phone instead of wrapping into a wall. */}
      <div className="-mx-5 flex gap-2 overflow-x-auto px-5 pb-1 [scrollbar-width:none] sm:mx-0 sm:flex-wrap sm:px-0">
        {fairs.map((fair) => (
          <Chip
            key={fair.id}
            active={choice.kind === "fair" && choice.fair.id === fair.id}
            onClick={() => onChoose({ kind: "fair", fair })}
            live={fair.ends_on >= today}
          >
            {fair.name}
          </Chip>
        ))}
        {SPAN_KEYS.map((key) => (
          <Chip key={key} active={choice.kind === "preset" && choice.key === key} onClick={() => onChoose({ kind: "preset", key })}>
            {SPAN_LABELS[key]}
          </Chip>
        ))}
      </div>
      <details className="group mt-3" open={choice.kind === "custom"}>
        <summary className="inline-flex cursor-pointer list-none items-center gap-2 text-small text-ink-secondary hover:text-ink">
          <span className="font-medium text-ink">{spanLabel(span)}</span>
          <span aria-hidden="true" className="text-ink-tertiary transition-transform group-open:rotate-90">
            ›
          </span>
          <span className="text-hint text-ink-tertiary">Eigener Zeitraum</span>
        </summary>
        <form
          className="mt-3 flex flex-wrap items-end gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (from && to && from <= to) {
              onChoose({ kind: "custom", span: { start: from, end: to } });
            }
          }}
        >
          <label className="text-hint text-ink-tertiary">
            Von
            <Input type="date" value={from} max={today} onChange={(event) => setFrom(event.target.value)} className="mt-1 w-44" />
          </label>
          <label className="text-hint text-ink-tertiary">
            Bis
            <Input type="date" value={to} max={today} onChange={(event) => setTo(event.target.value)} className="mt-1 w-44" />
          </label>
          <Button type="submit" size="sm" variant="secondary" disabled={!from || !to || from > to}>
            Anzeigen
          </Button>
        </form>
      </details>
    </section>
  );
}

/* --- Channels ------------------------------------------------------------------------ */

function Swatch({ channel, className }: { channel: ReportChannel; className?: string }) {
  return <span aria-hidden="true" className={cn("inline-block size-2.5 shrink-0", CHANNEL_SWATCHES[channel], className)} />;
}

function ChannelFilter({
  channels,
  total,
  value,
  onChange,
}: {
  channels: readonly ChannelShare[];
  total: number;
  value: ReportChannel | "all";
  onChange: (value: ReportChannel | "all") => void;
}) {
  if (channels.length < 2 && value === "all") {
    return null;
  }
  return (
    <div role="group" aria-label="Verkaufskanal" className="-mx-5 flex gap-2 overflow-x-auto px-5 [scrollbar-width:none] sm:mx-0 sm:flex-wrap sm:px-0">
      <Chip active={value === "all"} onClick={() => onChange("all")}>
        Alle <span className="tabular-nums opacity-70">{total}</span>
      </Chip>
      {channels.map((row) => (
        <Chip key={row.channel} active={value === row.channel} onClick={() => onChange(value === row.channel ? "all" : row.channel)}>
          <Swatch channel={row.channel} />
          {CHANNEL_LABELS[row.channel]} <span className="tabular-nums opacity-70">{row.sales}</span>
        </Chip>
      ))}
    </div>
  );
}

/* --- Headline ------------------------------------------------------------------------ */

function Headline({
  lines,
  channels,
  span,
  refreshing,
}: {
  lines: readonly SoldLineOut[];
  channels: readonly ChannelShare[];
  span: Span;
  refreshing: boolean;
}) {
  const sum = totals(lines);
  const average = sum.sales > 0 ? Math.round(sum.cents / sum.pieces) : 0;
  return (
    <section aria-label="Umsatz" className="border border-ink bg-surface shadow-hard">
      <div className="grid gap-6 p-5 sm:p-7 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-10">
        <div>
          <p className="flex items-center gap-2 label-caps text-ink-tertiary">
            Umsatz · brutto
            {refreshing ? <span aria-hidden="true" className="size-1.5 animate-lamp-pulse rounded-full bg-action" /> : null}
          </p>
          <p className="mt-2 font-display text-[2.75rem] leading-none font-extrabold tracking-[-0.04em] text-ink tabular-nums sm:text-display">
            {formatPrice(sum.cents)}
          </p>
          <dl className="mt-5 grid grid-cols-3 border-t border-line pt-4">
            <Figure label="Stück" value={sum.pieces.toLocaleString("de-DE")} />
            <Figure label="Verkäufe" value={sum.sales.toLocaleString("de-DE")} />
            <Figure label="Ø je Stück" value={sum.pieces > 0 ? formatPrice(average) : "–"} />
          </dl>
        </div>
        <div className="lg:border-l lg:border-line lg:pl-10">
          <p className="label-caps text-ink-tertiary">Nach Kanal</p>
          {sum.cents > 0 ? (
            <ChannelBar channels={channels} total={sum.cents} />
          ) : (
            <p className="mt-3 text-small text-ink-secondary">
              {span.start === span.end ? "An diesem Tag" : "In diesem Zeitraum"} wurde noch nichts verkauft.
            </p>
          )}
        </div>
      </div>
      {sum.estimatedPieces > 0 ? (
        <p className="border-t border-line bg-warning-subtle px-5 py-3 text-hint text-ink sm:px-7">
          <span className="font-medium">{piecesLabel(sum.estimatedPieces)} ohne eingetragenen Preis</span> zählen mit dem
          Shoppreis ({formatPrice(sum.estimatedCents)}). Unten bei „Preis eintragen“ korrigieren, wenn sie günstiger weggingen.
        </p>
      ) : null}
    </section>
  );
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-hint text-ink-tertiary">{label}</dt>
      <dd className="mt-0.5 truncate text-spec font-medium text-ink tabular-nums">{value}</dd>
    </div>
  );
}

function ChannelBar({ channels, total }: { channels: readonly ChannelShare[]; total: number }) {
  return (
    <div className="mt-3">
      <div
        role="img"
        aria-label={channels.map((row) => `${CHANNEL_LABELS[row.channel]} ${formatPrice(row.cents)}`).join(", ")}
        className="flex h-5 gap-0.5 border border-ink"
      >
        {channels
          .filter((row) => row.cents > 0)
          .map((row) => (
            <div
              key={row.channel}
              title={`${CHANNEL_LABELS[row.channel]}: ${formatPrice(row.cents)}`}
              className={cn("h-full transition-[width] duration-500 ease-out", CHANNEL_SWATCHES[row.channel])}
              style={{ width: `${share(row.cents, total)}%` }}
            />
          ))}
      </div>
      <dl className="mt-4 space-y-2.5">
        {channels.map((row) => (
          <div key={row.channel} className="flex items-baseline justify-between gap-3 text-small">
            <dt className="flex min-w-0 items-baseline gap-2 text-ink-secondary">
              <Swatch channel={row.channel} className="translate-y-px" />
              <span>{CHANNEL_LABELS[row.channel]}</span>
              <span className="shrink-0 text-hint text-ink-tertiary tabular-nums">
                {piecesLabel(row.pieces)} · {Math.round(share(row.cents, total))} %
              </span>
            </dt>
            <dd className="shrink-0 font-medium text-ink tabular-nums">{formatPrice(row.cents)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

/* --- Course -------------------------------------------------------------------------- */

type CourseRow = Tally & { key: string; label: string; sub?: string; channels: ChannelShare[] };

/** Day by day (or month by month for long spans) as horizontal bars: legible on a phone. */
function Course({ lines, span }: { lines: readonly SoldLineOut[]; span: Span }) {
  const days = daysOf(span).length;
  if (days < 2) {
    return null;
  }
  const rows: CourseRow[] =
    days <= DAILY_UP_TO
      ? byDay(lines, span).map((row) => ({ ...row, key: row.day, label: weekdayLabel(row.day) }))
      : byMonth(lines, span).map((row) => ({ ...row, key: row.month, label: monthLabel(row.month) }));
  const peak = Math.max(...rows.map((row) => row.cents), 1);
  return (
    <Panel title={days <= DAILY_UP_TO ? "Verlauf nach Tagen" : "Verlauf nach Monaten"}>
      <ol className="space-y-1.5">
        {rows.map((row) => (
          <li key={row.key} className="grid grid-cols-[5.5rem_minmax(0,1fr)_auto] items-center gap-3 text-small sm:grid-cols-[9rem_minmax(0,1fr)_9rem]">
            <span className={cn("truncate tabular-nums", row.cents > 0 ? "text-ink" : "text-ink-tertiary")}>{row.label}</span>
            <span className="flex h-3.5 gap-px" title={`${row.label}: ${formatPrice(row.cents)} · ${piecesLabel(row.pieces)}`}>
              {row.cents > 0 ? (
                row.channels.map((part) => (
                  <span
                    key={part.channel}
                    className={cn("h-full origin-left animate-bar-grow", CHANNEL_SWATCHES[part.channel])}
                    style={{ width: `${share(part.cents, peak)}%` }}
                  />
                ))
              ) : (
                <span className="h-px w-full self-center bg-line" />
              )}
            </span>
            <span className={cn("text-right tabular-nums", row.cents > 0 ? "font-medium text-ink" : "text-ink-tertiary")}>
              {row.cents > 0 ? formatPrice(row.cents) : "–"}
            </span>
          </li>
        ))}
      </ol>
    </Panel>
  );
}

/* --- List ---------------------------------------------------------------------------- */

function SaleList({ lines }: { lines: readonly SoldLineOut[] }) {
  const [editing, setEditing] = useState<SoldLineOut | null>(null);
  const groups = useMemo(() => {
    const byDayKey = new Map<string, SoldLineOut[]>();
    for (const line of lines) {
      const day = shopDay(line.sold_at);
      byDayKey.set(day, [...(byDayKey.get(day) ?? []), line]);
    }
    return [...byDayKey.entries()];
  }, [lines]);

  if (lines.length === 0) {
    return null;
  }
  return (
    <Panel title="Alle Verkäufe" actions={<span className="text-hint text-ink-tertiary">{lines.length} Einträge</span>}>
      <div className="-mx-5 -my-5">
        {groups.map(([day, dayLines]) => {
          const sum = totals(dayLines);
          return (
            <section key={day} aria-label={longDayLabel(day)}>
              <h3 className="sticky top-0 z-[1] flex items-baseline justify-between gap-3 border-b border-line bg-sunken px-5 py-2 text-small font-medium">
                <span>{longDayLabel(day)}</span>
                <span className="tabular-nums">
                  {formatPrice(sum.cents)} <span className="font-normal text-ink-tertiary">· {piecesLabel(sum.pieces)}</span>
                </span>
              </h3>
              <ul className="divide-y divide-line">
                {dayLines.map((line) => (
                  <SaleRow key={line.key} line={line} onEdit={() => setEditing(line)} />
                ))}
              </ul>
            </section>
          );
        })}
      </div>
      <EditSaleDialog line={editing} onClose={() => setEditing(null)} />
    </Panel>
  );
}

function SaleRow({ line, onEdit }: { line: SoldLineOut; onEdit: () => void }) {
  const href: Route | null = line.order_id
    ? (`/admin/bestellungen/${line.order_id}` as Route)
    : line.unit_code
      ? (`/admin/lager/einheiten/${line.unit_code}` as Route)
      : null;
  return (
    <li className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-1 px-5 py-3.5">
      <div className="min-w-0">
        <p className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-hint text-ink-tertiary">
          <span className="tabular-nums">{timeLabel(line.sold_at)}</span>
          <span className="inline-flex items-center gap-1.5 font-medium text-ink-secondary">
            <Swatch channel={line.channel} />
            {CHANNEL_LABELS[line.channel]}
          </span>
          {line.order_number ? <span>Bestellung {line.order_number}</span> : null}
          {line.staff_name ? <span>{line.staff_name}</span> : null}
        </p>
        <p className="mt-1 text-small font-medium text-ink">
          {href ? (
            <Link href={href} className="hover:text-accent hover:underline hover:underline-offset-2">
              {line.title}
            </Link>
          ) : (
            line.title
          )}
        </p>
        {line.note ? <p className="mt-0.5 text-hint text-ink-secondary">„{line.note}“</p> : null}
      </div>
      <div className="text-right">
        <p className="text-small font-medium text-ink tabular-nums">{formatPrice(line.total_cents)}</p>
        <p className="text-hint text-ink-tertiary tabular-nums">
          {line.quantity > 1 ? `${line.quantity} × ${formatPrice(line.unit_price_cents)}` : null}
          {line.price_from_shop ? <span className="font-medium text-warning">Shoppreis</span> : null}
        </p>
      </div>
      {line.kind === "piece" ? (
        <div className="col-span-2">
          <button
            type="button"
            onClick={onEdit}
            className={cn(
              "inline-flex h-9 items-center text-hint font-medium underline-offset-2 hover:underline",
              line.price_from_shop || line.channel === "unknown" ? "text-accent" : "text-ink-tertiary",
            )}
          >
            {line.price_from_shop || line.channel === "unknown" ? "Preis eintragen" : "Kanal oder Preis ändern"}
          </button>
        </div>
      ) : null}
    </li>
  );
}

function EditSaleDialog({ line, onClose }: { line: SoldLineOut | null; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<SaleDraft>(saleDraft(null, "fair"));
  const [submitted, setSubmitted] = useState(false);
  const [shownFor, setShownFor] = useState<string | null>(null);
  // A fresh draft for each piece opened: its channel (or the last one used) and its price.
  if (line && shownFor !== line.key) {
    setShownFor(line.key);
    setSubmitted(false);
    setDraft(
      line.price_from_shop
        ? saleDraft(line.unit_price_cents, line.channel === "unknown" ? undefined : (line.channel as SaleChannel))
        : saleDraft(line.unit_price_cents, line.channel === "unknown" ? "" : (line.channel as SaleChannel)),
    );
  }
  const save = useMutation<UnitOut, ApiProblem, { channel: SaleChannel | null; price_cents: number | null }>({
    mutationFn: (sale) => recordUnitSale(line?.unit_code ?? "", sale),
    onSuccess() {
      void queryClient.invalidateQueries({ queryKey: getGetSalesReportQueryKey().slice(0, 1) });
      setShownFor(null);
      onClose();
    },
  });
  return (
    <Dialog
      open={line !== null}
      onOpenChange={(open) => {
        if (!open) {
          setShownFor(null);
          save.reset();
          onClose();
        }
      }}
    >
      <DialogContent className="max-w-lg">
        <DialogTitle>Verkauf eintragen</DialogTitle>
        <DialogDescription>{line?.title}</DialogDescription>
        <form
          noValidate
          className="mt-6 space-y-5"
          onSubmit={(event) => {
            event.preventDefault();
            setSubmitted(true);
            const sale = saleOf(draft);
            if (sale) {
              save.mutate(sale);
            }
          }}
        >
          <SaleFields value={draft} onChange={setDraft} shopPriceCents={line?.price_from_shop ? line.unit_price_cents : null} showErrors={submitted} />
          {save.error ? (
            <p role="alert" className="text-small text-danger">
              {errorMessage(save.error)}
            </p>
          ) : null}
          <div className="flex flex-wrap justify-end gap-3">
            <DialogClose asChild>
              <Button type="button" variant="secondary" size="sm">
                Abbrechen
              </Button>
            </DialogClose>
            <Button type="submit" size="sm" disabled={save.isPending} aria-busy={save.isPending || undefined}>
              {save.isPending ? "Wird gespeichert …" : "Speichern"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
