"use client";

import { useMemo, useState } from "react";

import { Panel } from "@/components/admin/panel";
import { useListStock } from "@/lib/api/generated/admin-inventory/admin-inventory";
import { useGetSalesReport } from "@/lib/api/generated/admin-sales/admin-sales";
import type { AdminFairOut, ReportChannel, SoldLineOut, StockOut } from "@/lib/api/generated/model";
import { formatPrice } from "@/lib/catalog/format";
import {
  fairResults,
  forecast,
  piecesByKey,
  previousSpan,
  rank,
  RANK_LABELS,
  stockChecks,
  type FairResult,
  type Forecast,
  type RankBy,
  type RankRow,
  type StockCheck,
} from "@/lib/sales/insights";
import { addDays, CHANNEL_LABELS, daysOf, longDayLabel, piecesLabel, share, shopDay, spanLabel, totals, type Span } from "@/lib/sales/report";
import { cn } from "@/lib/utils";

/** The fair comparison looks back one year; it changes slowly, so it reloads rarely. */
const YEAR_REFRESH_MS = 5 * 60_000;
const SHOWN = 6;

type SalesInsightsProps = {
  /** The span's sales, already filtered by channel. */
  lines: readonly SoldLineOut[];
  span: Span;
  filter: ReportChannel | "all";
  /** The fair chosen as the span, if any: the forecast then runs to its last day. */
  fair: AdminFairOut | null;
  fairs: readonly AdminFairOut[];
  onChooseFair: (fair: AdminFairOut) => void;
};

/**
 * Auswertung (ADR 0042): what sells best, where the pace leads, whether the shelf keeps up,
 * and how the fairs compare. Everything is counted from the report lines in the browser.
 */
export function SalesInsights({ lines, span, filter, fair, fairs, onChooseFair }: SalesInsightsProps) {
  const [by, setBy] = useState<RankBy>("model");
  const rows = useMemo(() => rank(lines, by), [lines, by]);

  // The trend compares with the span just before, as long as this one; a fair has no "before".
  const before = previousSpan(span);
  const previous = useGetSalesReport(before, { query: { enabled: fair === null, staleTime: 5 * 60_000 } });
  const trend = useMemo(() => {
    if (fair !== null || !previous.data) {
      return null;
    }
    const earlier = filter === "all" ? previous.data.lines : previous.data.lines.filter((line) => line.channel === filter);
    return piecesByKey(earlier, by);
  }, [fair, previous.data, filter, by]);

  const projection = useMemo(() => forecast(lines, span, fair), [lines, span, fair]);
  const stock = useListStock({ query: { enabled: projection !== null, staleTime: 60_000, select: freeByVariant } });
  const checks = useMemo(() => {
    if (!projection || !stock.data) {
      return [];
    }
    return stockChecks(rank(lines, "variant"), stock.data, projection.pace.days, projection.daysLeft).filter((check) => check.variantIds.length > 0);
  }, [projection, stock.data, lines]);

  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <BestSellers rows={rows} by={by} onBy={setBy} trend={trend} trendLabel={spanLabel(before)} />
        {projection ? <ForecastPanel forecast={projection} checks={checks} filter={filter} fair={fair} /> : <NoForecast span={span} />}
      </div>
      <FairsCompared fairs={fairs} chosen={fair} onChoose={onChooseFair} />
    </div>
  );
}

function freeByVariant(stock: StockOut): Map<string, number> {
  return new Map(stock.items.map((item) => [item.variant_id, item.in_stock]));
}

/* --- Best sellers -------------------------------------------------------------------- */

const RANK_KEYS: readonly RankBy[] = ["model", "scale", "variant"];

function BestSellers({
  rows,
  by,
  onBy,
  trend,
  trendLabel,
}: {
  rows: readonly RankRow[];
  by: RankBy;
  onBy: (by: RankBy) => void;
  trend: ReadonlyMap<string, number> | null;
  trendLabel: string;
}) {
  const [all, setAll] = useState(false);
  const top = rows[0]?.cents ?? 0;
  const total = rows.reduce((sum, row) => sum + row.cents, 0);
  const shown = all ? rows : rows.slice(0, SHOWN);
  return (
    <Panel
      title="Was läuft am besten?"
      actions={
        <div role="group" aria-label="Auswerten nach" className="flex border border-line-control">
          {RANK_KEYS.map((key) => (
            <button
              key={key}
              type="button"
              aria-pressed={by === key}
              onClick={() => onBy(key)}
              className={cn(
                "h-8 px-3 text-hint font-medium transition-colors",
                by === key ? "bg-ink text-on-selected" : "bg-surface text-ink-secondary hover:text-ink",
              )}
            >
              {RANK_LABELS[key]}
            </button>
          ))}
        </div>
      }
    >
      {rows.length === 0 ? (
        <p className="text-small text-ink-secondary">Noch keine Verkäufe in diesem Zeitraum: Sobald etwas weggeht, steht es hier.</p>
      ) : (
        <>
          <ol className="space-y-4">
            {shown.map((row, index) => (
              <li key={row.key} className="grid grid-cols-[2rem_minmax(0,1fr)_auto] items-start gap-x-3 animate-feed-in">
                <span
                  className={cn(
                    "font-display text-[1.75rem] leading-none font-extrabold tracking-[-0.04em] tabular-nums",
                    index === 0 ? "text-action" : "text-ink-tertiary",
                  )}
                >
                  {index + 1}
                </span>
                <div className="min-w-0">
                  <p className="flex flex-wrap items-baseline gap-x-2 text-small font-medium text-ink">
                    <span className="min-w-0 break-words">{row.label}</span>
                    {trend ? <Trend now={row.pieces} before={trend.get(row.key) ?? 0} label={trendLabel} /> : null}
                  </p>
                  {row.detail ? <p className="truncate text-hint text-ink-tertiary">{row.detail}</p> : null}
                  <div className="mt-2 h-2 bg-sunken" aria-hidden="true">
                    <div
                      className={cn("h-full origin-left animate-bar-grow", index === 0 ? "bg-action" : "bg-ink")}
                      style={{ width: `${share(row.cents, top)}%` }}
                    />
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-small font-medium text-ink tabular-nums">{formatPrice(row.cents)}</p>
                  <p className="text-hint text-ink-tertiary tabular-nums">
                    {piecesLabel(row.pieces)} · Ø {formatPrice(row.averageCents)}
                  </p>
                  <p className="text-hint text-ink-tertiary tabular-nums">{Math.round(share(row.cents, total))} % vom Umsatz</p>
                </div>
              </li>
            ))}
          </ol>
          {rows.length > SHOWN ? (
            <button
              type="button"
              onClick={() => setAll(!all)}
              className="mt-4 inline-flex h-9 items-center text-hint font-medium text-accent underline-offset-2 hover:underline"
            >
              {all ? "Weniger zeigen" : `Alle ${rows.length} zeigen`}
            </button>
          ) : null}
        </>
      )}
    </Panel>
  );
}

/** Pieces against the span before: up, down, or new. */
function Trend({ now, before, label }: { now: number; before: number; label: string }) {
  const title = `Davor (${label}): ${piecesLabel(before)}`;
  if (before === 0) {
    return (
      <span title={title} className="bg-accent-subtle px-1.5 text-[0.6875rem] leading-5 font-semibold tracking-wide text-accent uppercase">
        neu
      </span>
    );
  }
  const change = now - before;
  if (change === 0) {
    return (
      <span title={title} className="text-hint text-ink-tertiary">
        ±0
      </span>
    );
  }
  return (
    <span title={title} className={cn("text-hint font-semibold tabular-nums", change > 0 ? "text-success" : "text-danger")}>
      <span aria-hidden="true">{change > 0 ? "▲" : "▼"}</span> {change > 0 ? "+" : "−"}
      {Math.abs(change)} <span className="sr-only">Stück gegenüber {label}</span>
    </span>
  );
}

/* --- Forecast ------------------------------------------------------------------------ */

function ForecastPanel({
  forecast: projection,
  checks,
  filter,
  fair,
}: {
  forecast: Forecast;
  checks: readonly StockCheck[];
  filter: ReportChannel | "all";
  fair: AdminFairOut | null;
}) {
  const isFair = projection.kind === "fair";
  const soldCents = isFair ? projection.cents - Math.round(projection.pace.centsPerDay * projection.daysLeft) : 0;
  const lastDay = fair ? longDayLabel(fair.ends_on).split(",")[0] : "";
  const scope = filter === "all" ? "alle Kanäle" : CHANNEL_LABELS[filter];
  return (
    <Panel
      title="Prognose"
      actions={<span className="text-hint text-ink-tertiary">{isFair ? `Tag ${projection.dayNumber} von ${projection.daysTotal}` : `nächste ${projection.daysLeft} Tage`}</span>}
    >
      <p className="label-caps text-ink-tertiary">{isFair ? `Hochgerechnet bis ${lastDay}` : "Bei gleichem Tempo"} · {scope}</p>
      <p className="mt-2 font-display text-[2.25rem] leading-none font-extrabold tracking-[-0.04em] text-ink tabular-nums">
        {isFair ? "" : "+ "}
        {formatPrice(projection.cents)}
      </p>
      <p className="mt-1.5 text-small text-ink-secondary tabular-nums">
        ≈ {piecesLabel(projection.pieces)}
        {isFair ? " insgesamt" : " in 30 Tagen"}
      </p>

      {isFair ? (
        <div className="mt-5">
          <div
            role="img"
            aria-label={`Bisher ${formatPrice(soldCents)}, erwartet ${formatPrice(projection.cents)}`}
            className="flex h-4 border border-ink"
          >
            <div className="h-full origin-left animate-bar-grow bg-action" style={{ width: `${share(soldCents, projection.cents)}%` }} />
            <div className="stellwerk-hatch h-full flex-1 bg-surface text-action/50" />
          </div>
          <div className="mt-2 flex justify-between text-hint text-ink-tertiary tabular-nums">
            <span>
              <span className="font-medium text-ink">{formatPrice(soldCents)}</span> bisher
            </span>
            <span>
              {projection.daysLeft > 0 ? `+ ${formatPrice(projection.cents - soldCents)} erwartet` : "letzter Tag"}
            </span>
          </div>
        </div>
      ) : null}

      <dl className="mt-5 grid grid-cols-2 border-t border-line pt-4">
        <div>
          <dt className="text-hint text-ink-tertiary">Je {isFair ? "Messetag" : "Tag"}</dt>
          <dd className="mt-0.5 text-spec font-medium text-ink tabular-nums">{formatPrice(Math.round(projection.pace.centsPerDay))}</dd>
        </div>
        <div>
          <dt className="text-hint text-ink-tertiary">Stück je Tag</dt>
          <dd className="mt-0.5 text-spec font-medium text-ink tabular-nums">
            {projection.pace.piecesPerDay.toLocaleString("de-DE", { maximumFractionDigits: 1 })}
          </dd>
        </div>
      </dl>
      <p className="mt-3 text-hint text-ink-tertiary">
        {isFair
          ? "Gerechnet mit dem Schnitt der bisherigen Messetage; der heutige zählt schon voll, morgens ist die Zahl daher vorsichtig."
          : `Gerechnet mit dem Schnitt der letzten ${projection.pace.days} Tage.`}
      </p>

      {checks.length > 0 ? (
        <div className="mt-6 border-t border-line pt-4">
          <p className="label-caps text-ink-tertiary">Reicht der Bestand?</p>
          <ul className="mt-3 space-y-2">
            {checks.map((check) => (
              <StockRow key={check.key} check={check} isFair={isFair} />
            ))}
          </ul>
        </div>
      ) : null}
    </Panel>
  );
}

const TONES: Record<StockCheck["tone"], { box: string; text: string }> = {
  ok: { box: "border-line bg-surface", text: "text-success" },
  tight: { box: "border-warning/40 bg-warning-subtle", text: "text-warning" },
  short: { box: "border-danger/40 bg-danger-subtle", text: "text-danger" },
};

function StockRow({ check, isFair }: { check: StockCheck; isFair: boolean }) {
  const tone = TONES[check.tone];
  const until = isFair ? "bis Messeende" : "in 30 Tagen";
  const verdict =
    check.tone === "short"
      ? check.free === 0
        ? "Nichts mehr frei"
        : `Reicht nur ~${check.lastsDays ?? 0} ${check.lastsDays === 1 ? "Tag" : "Tage"}`
      : check.tone === "tight"
        ? "Wird knapp"
        : "Reicht";
  return (
    <li className={cn("grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border px-3 py-2", tone.box)}>
      <div className="min-w-0">
        <p className="line-clamp-2 text-small font-medium text-ink">{check.label}</p>
        <p className="text-hint text-ink-tertiary tabular-nums">
          {check.free} frei · gebraucht {until} ≈ {check.wanted}
        </p>
      </div>
      <span className={cn("text-hint font-semibold whitespace-nowrap", tone.text)}>{verdict}</span>
    </li>
  );
}

function NoForecast({ span }: { span: Span }) {
  const past = span.end < shopDay(new Date());
  return (
    <Panel title="Prognose">
      <p className="text-small text-ink-secondary">
        {past
          ? "Dieser Zeitraum ist vorbei, da gibt es nichts mehr hochzurechnen."
          : "Eine Prognose gibt es während einer Messe (Messe oben wählen) oder ab sieben Tagen mit Verkäufen, etwa mit „30 Tage“."}
      </p>
    </Panel>
  );
}

/* --- Fairs compared ------------------------------------------------------------------ */

function FairsCompared({ fairs, chosen, onChoose }: { fairs: readonly AdminFairOut[]; chosen: AdminFairOut | null; onChoose: (fair: AdminFairOut) => void }) {
  const today = shopDay(new Date());
  const year: Span = { start: addDays(today, -365), end: today };
  const begun = fairs.some((fair) => fair.starts_on <= today && fair.ends_on >= year.start);
  const report = useGetSalesReport(year, { query: { enabled: begun, refetchInterval: YEAR_REFRESH_MS, staleTime: 60_000 } });
  const results = useMemo(
    () => (report.data ? fairResults(report.data.lines, fairs.filter((fair) => fair.ends_on >= year.start)) : []),
    [report.data, fairs, year.start],
  );
  if (!begun || results.length === 0) {
    return null;
  }
  const best = Math.max(...results.map((result) => result.centsPerDay), 1);
  const sum = totals(report.data?.lines.filter((line) => line.channel === "fair") ?? []);
  return (
    <Panel
      title="Messen im Vergleich"
      actions={
        <span className="text-hint text-ink-tertiary tabular-nums">
          letzte 12 Monate · {formatPrice(sum.cents)} auf {results.length} {results.length === 1 ? "Messe" : "Messen"}
        </span>
      }
    >
      <ul className="-mx-5 -my-5 divide-y divide-line">
        {results.map((result) => (
          <FairRow key={result.fair.id} result={result} best={best} active={chosen?.id === result.fair.id} onChoose={() => onChoose(result.fair)} />
        ))}
      </ul>
    </Panel>
  );
}

function FairRow({ result, best, active, onChoose }: { result: FairResult; best: number; active: boolean; onChoose: () => void }) {
  const total = daysOf({ start: result.fair.starts_on, end: result.fair.ends_on }).length;
  return (
    <li>
      <button
        type="button"
        onClick={onChoose}
        aria-pressed={active}
        className={cn(
          "grid w-full grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-2 px-5 py-4 text-left transition-colors sm:grid-cols-[minmax(0,2fr)_minmax(0,3fr)_8rem]",
          active ? "bg-accent-subtle" : "hover:bg-canvas",
        )}
      >
        <div className="min-w-0">
          <p className="flex items-center gap-2 text-small font-medium text-ink">
            {result.running ? <span aria-hidden="true" className="size-2 shrink-0 animate-lamp-pulse rounded-full bg-action" /> : null}
            <span className="truncate">{result.fair.name}</span>
          </p>
          <p className="text-hint text-ink-tertiary">
            {result.fair.when || spanLabel({ start: result.fair.starts_on, end: result.fair.ends_on })}
            {result.fair.city ? ` · ${result.fair.city}` : ""}
            {result.running ? ` · läuft, Tag ${result.days} von ${total}` : ""}
          </p>
        </div>
        <div className="order-last col-span-2 min-w-0 sm:order-none sm:col-span-1">
          <div className="flex items-center gap-3">
            <div className="h-2 flex-1 bg-sunken" aria-hidden="true">
              <div className="h-full origin-left animate-bar-grow bg-action" style={{ width: `${share(result.centsPerDay, best)}%` }} />
            </div>
            <span className="w-24 shrink-0 text-right text-hint text-ink-secondary tabular-nums">{formatPrice(result.centsPerDay)} / Tag</span>
          </div>
          <p className="mt-1 truncate text-hint text-ink-tertiary">
            {result.top ? (
              <>
                Bestseller: <span className="text-ink-secondary">{result.top.label}</span> ({piecesLabel(result.top.pieces)})
              </>
            ) : (
              "Noch nichts verkauft"
            )}
          </p>
        </div>
        <div className="text-right">
          <p className="text-small font-medium text-ink tabular-nums">{formatPrice(result.cents)}</p>
          <p className="text-hint text-ink-tertiary tabular-nums">{piecesLabel(result.pieces)}</p>
        </div>
      </button>
    </li>
  );
}
