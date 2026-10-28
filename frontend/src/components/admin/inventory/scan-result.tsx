"use client";

import type { Route } from "next";
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { StatusBadge, type StatusTone } from "@/components/ui/status-badge";
import type { ScanOut } from "@/lib/api/generated/model";
import { formatUnitCode } from "@/lib/inventory/codes";
import {
  LOCATION_KIND_LABELS,
  OUTCOME_LABELS,
  OUTCOME_TONES,
  scanHeadline,
  UNIT_STATUS_LABELS,
} from "@/lib/inventory/labels";
import type { ScanEntry } from "@/lib/inventory/scan-session";
import { cn } from "@/lib/utils";

/** How long the big card offers to take a booking back (the server allows longer). */
export const UNDO_OFFER_MS = 10_000;

const FRAME: Readonly<Record<StatusTone, string>> = {
  success: "border-success bg-success-subtle",
  accent: "border-accent bg-accent-subtle",
  neutral: "border-line-strong bg-surface",
  warning: "border-warning bg-warning-subtle",
  danger: "border-danger bg-danger-subtle",
};

function toneOf(entry: ScanEntry): StatusTone {
  if (entry.state === "failed") {
    return "danger";
  }
  if (entry.state === "waiting" || entry.answer === undefined) {
    return "warning";
  }
  return entry.answer.undone ? "neutral" : OUTCOME_TONES[entry.answer.outcome];
}

const clock = new Intl.DateTimeFormat("de-DE", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

export function scanTime(entry: ScanEntry): string {
  return clock.format(new Date(entry.at));
}

/** What a history line says about a scan. */
export function entrySummary(entry: ScanEntry): string {
  if (entry.state === "sending") {
    return "Wird geprüft …";
  }
  if (entry.state === "waiting") {
    return "Ohne Netz: wird nachgereicht.";
  }
  if (entry.state === "failed" || entry.answer === undefined) {
    return entry.error ?? "Fehlgeschlagen.";
  }
  return scanHeadline(entry.answer);
}

/** Seconds left to take the scan back; 0 once the offer is over. */
function useUndoCountdown(entry: ScanEntry): number {
  const offered = entry.answer?.undoable === true && !entry.answer.undone;
  const [now, setNow] = useState(entry.at);
  useEffect(() => {
    if (!offered) {
      return;
    }
    const tick = () => setNow(Date.now());
    tick();
    const timer = setInterval(tick, 250);
    return () => clearInterval(timer);
  }, [offered, entry.scanId]);
  return offered ? Math.max(0, Math.ceil((entry.at + UNDO_OFFER_MS - now) / 1000)) : 0;
}

type ScanResultProps = {
  entry: ScanEntry;
  /** A scan is on its way to the server right now. */
  checking: boolean;
  onUndo: (scanId: string) => void;
  undoing: boolean;
  /** Links to unit and location pages (hidden on the phone, where they lead away). */
  showLinks?: boolean;
};

/** The latest scan, large: readable at arm's length with a parcel in the other hand. */
export function ScanResult({ entry, checking, onUndo, undoing, showLinks = true }: ScanResultProps) {
  const tone = toneOf(entry);
  const secondsLeft = useUndoCountdown(entry);
  const answer = entry.state === "answered" ? entry.answer : undefined;

  return (
    <article
      aria-live="polite"
      aria-busy={checking || undefined}
      className={cn("rounded-md border-l-4 border-y border-r p-5 transition-colors", FRAME[tone], checking && "opacity-70")}
    >
      <header className="flex items-center justify-between gap-3">
        <StatusBadge tone={tone} busy={checking}>
          {answer ? (answer.undone ? "Zurückgenommen" : OUTCOME_LABELS[answer.outcome]) : entry.state === "waiting" ? "Wartet auf Netz" : "Fehler"}
        </StatusBadge>
        <time className="font-mono text-hint text-ink-tertiary tabular-nums" dateTime={new Date(entry.at).toISOString()}>
          {scanTime(entry)}
        </time>
      </header>
      <p className="mt-3 text-[1.375rem] leading-7 font-medium tracking-[-0.01em] text-balance">{entrySummary(entry)}</p>
      {answer ? <AnswerDetails answer={answer} raw={entry.raw} showLinks={showLinks} /> : <RawCode raw={entry.raw} />}
      {secondsLeft > 0 ? (
        <div className="mt-5 flex items-center gap-3">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={undoing}
            aria-busy={undoing || undefined}
            onClick={() => onUndo(entry.scanId)}
          >
            {undoing ? "Wird zurückgenommen …" : "Rückgängig"}
          </Button>
          <UndoRing seconds={secondsLeft} />
        </div>
      ) : null}
    </article>
  );
}

/** A ring that runs down with the undo offer. */
function UndoRing({ seconds }: { seconds: number }) {
  const total = UNDO_OFFER_MS / 1000;
  const circumference = 2 * Math.PI * 9;
  return (
    <span className="flex items-center gap-2 text-hint text-ink-tertiary">
      <svg aria-hidden="true" viewBox="0 0 24 24" className="size-5 -rotate-90">
        <circle cx="12" cy="12" r="9" fill="none" stroke="var(--line)" strokeWidth="2.5" />
        <circle
          cx="12"
          cy="12"
          r="9"
          fill="none"
          stroke="var(--ink-secondary)"
          strokeWidth="2.5"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - seconds / total)}
          className="transition-[stroke-dashoffset] duration-300"
        />
      </svg>
      <span className="tabular-nums">noch {seconds} s</span>
    </span>
  );
}

function RawCode({ raw }: { raw: string }) {
  return <p className="mt-3 font-mono text-small break-all text-ink-secondary">{raw}</p>;
}

function Line({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-ink-tertiary">{label}</dt>
      <dd className="min-w-0">{children}</dd>
    </>
  );
}

function AnswerDetails({ answer, raw, showLinks }: { answer: ScanOut; raw: string; showLinks: boolean }) {
  const { unit, location, variant, effect, progress, next_expected: next } = answer;
  const resolved = answer.resolved;
  const code =
    resolved === null ? null : resolved.kind === "unit" ? formatUnitCode(resolved.code) : resolved.code;
  return (
    <>
      {code !== null ? (
        <p className="mt-2 font-mono text-[1.125rem] leading-6 font-medium tracking-wide">
          {showLinks && resolved?.kind === "unit" ? (
            <Link href={`/admin/lager/einheiten/${resolved.code}` as Route} className="hover:underline">
              {code}
            </Link>
          ) : showLinks && resolved?.kind === "location" ? (
            <Link href={`/admin/lager/plaetze/${resolved.code}` as Route} className="hover:underline">
              {code}
            </Link>
          ) : (
            code
          )}
        </p>
      ) : (
        <RawCode raw={raw} />
      )}
      <dl className="mt-4 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1.5 text-small">
        {unit ? (
          <>
            <Line label="Artikel">
              {unit.title ?? "Unbekannter Artikel"}
              {unit.sku ? <span className="ml-2 font-mono text-hint text-ink-tertiary">{unit.sku}</span> : null}
            </Line>
            <Line label="Zustand">{UNIT_STATUS_LABELS[unit.status]}</Line>
            {unit.location_code ? <Line label="Platz">{<span className="font-mono">{unit.location_code}</span>}</Line> : null}
            {unit.order_number ? <Line label="Für">{<span className="font-mono">{unit.order_number}</span>}</Line> : null}
          </>
        ) : null}
        {variant ? (
          <>
            <Line label="Artikel">
              {variant.title}
              <span className="ml-2 font-mono text-hint text-ink-tertiary">{variant.sku}</span>
            </Line>
            <Line label="Im Lager">{variant.free_units === 1 ? "1 Stück frei" : `${variant.free_units} Stück frei`}</Line>
          </>
        ) : null}
        {location && !unit ? (
          <>
            <Line label="Platz">
              {location.name || LOCATION_KIND_LABELS[location.kind]}
              <span className="ml-2 text-hint text-ink-tertiary">{LOCATION_KIND_LABELS[location.kind]}</span>
            </Line>
            <Line label="Inhalt">{location.unit_count === 1 ? "1 Stück" : `${location.unit_count} Stück`}</Line>
          </>
        ) : null}
        {effect && (effect.from_location || effect.to_location) && !answer.undone ? (
          <Line label="Weg">
            <span className="inline-flex flex-wrap items-center gap-2 font-mono">
              <span className={cn(!effect.from_location && "text-ink-tertiary")}>{effect.from_location ?? "neu"}</span>
              <span aria-label="nach">→</span>
              <span className="font-medium">{effect.to_location ?? UNIT_STATUS_LABELS[effect.to_status]}</span>
            </span>
          </Line>
        ) : null}
        {effect?.reserved_for ? <Line label="Reserviert">{<span className="font-mono">{effect.reserved_for}</span>}</Line> : null}
        {progress ? (
          <Line label="Fortschritt">
            <span className="tabular-nums">
              {progress.picked} von {progress.total}
            </span>
          </Line>
        ) : null}
      </dl>
      {next ? (
        <div className="mt-4 rounded-sm border border-accent/40 bg-surface px-4 py-3">
          <p className="label-caps text-accent">Als Nächstes</p>
          <p className="mt-1 text-small font-medium">{next.title}</p>
          <p className="mt-0.5 flex flex-wrap gap-x-3 font-mono text-hint text-ink-secondary">
            <span>{next.location_code ?? "noch in Fertigung"}</span>
            {next.location_name ? <span className="font-sans">{next.location_name}</span> : null}
            {next.unit_code ? <span>{formatUnitCode(next.unit_code)}</span> : null}
          </p>
        </div>
      ) : null}
    </>
  );
}
