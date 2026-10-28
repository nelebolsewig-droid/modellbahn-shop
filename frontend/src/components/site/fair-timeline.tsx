import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import type { FairOut } from "@/lib/api/generated/model";
import { countdown, dateBlock, fairEventUrl, hourLines, place, routeUrl } from "@/lib/site/fairs";
import { cn } from "@/lib/utils";

/*
 * The fairs as stops on a line, drawn like a route map: a fine line from station to
 * station, the next stop filled in the accent colour. Past fairs continue the line
 * dashed and small, as a look back.
 */

const ICON = "size-4 shrink-0";
const ACTION_LINK =
  "inline-flex items-center gap-2 rounded-xs text-sm font-medium text-accent underline-offset-4 hover:text-accent-hover hover:underline";

function CalendarIcon() {
  return (
    <svg viewBox="0 0 16 16" className={ICON} fill="none" stroke="currentColor" strokeWidth="1.3" aria-hidden="true">
      <rect x="2" y="3" width="12" height="11" rx="1.5" />
      <path d="M2 6.5h12M5.5 1.5v3M10.5 1.5v3" />
      <path d="M8 8.5v3M6.5 10h3" />
    </svg>
  );
}

function RouteIcon() {
  return (
    <svg viewBox="0 0 16 16" className={ICON} fill="none" stroke="currentColor" strokeWidth="1.3" aria-hidden="true">
      <circle cx="4" cy="12" r="1.75" />
      <circle cx="12" cy="4" r="1.75" />
      <path d="M5.75 12H10a2 2 0 0 0 0-4H6a2 2 0 0 1 0-4h4.25" />
    </svg>
  );
}

function ExternalIcon() {
  return (
    <svg viewBox="0 0 16 16" className={ICON} fill="none" stroke="currentColor" strokeWidth="1.3" aria-hidden="true">
      <path d="M9 2.5h4.5V7M13.5 2.5 7.5 8.5" />
      <path d="M12 9.5v3a1 1 0 0 1-1 1H3.5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h3" />
    </svg>
  );
}

/** The booth as a platform sign: white on Prussian blue. */
export function BoothSign({ children }: { children: string }) {
  return (
    <span className="inline-flex items-center rounded-xs bg-accent px-2.5 py-1 font-mono text-small font-medium tracking-[0.02em] text-on-accent">
      {children}
    </span>
  );
}

/** The date of a fair, large: "20.–22." over "Nov 2026 · Fr–So". */
export function FairDate({ fair, size = "large" }: { fair: FairOut; size?: "large" | "medium" }) {
  const block = dateBlock(fair);
  return (
    <p className="flex flex-col">
      <span className="sr-only">{fair.when}</span>
      <span
        aria-hidden="true"
        className={cn(
          "font-extralight tabular-nums",
          size === "large" && (block.long ? "text-title" : "text-display"),
          size === "medium" && (block.long ? "text-heading" : "text-title"),
        )}
      >
        {block.days}
      </span>
      <span aria-hidden="true" className="mt-2 label-caps text-ink-tertiary">
        {block.months} · {block.weekdays}
      </span>
    </p>
  );
}

type StationProps = { kind: "next" | "later" | "past"; running?: boolean };

function Station({ kind, running = false }: StationProps) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "absolute left-0 rounded-full",
        kind === "next" && "top-9 size-4 border-2 border-accent bg-accent shadow-[0_0_0_5px_var(--accent-subtle)]",
        kind === "next" && running && "animate-lamp-pulse",
        kind === "later" && "top-9 size-4 border-2 border-ink bg-canvas",
        kind === "past" && "top-2 left-[3px] size-2.5 border border-ink-tertiary bg-canvas",
      )}
    />
  );
}

function Detail({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div>
      <dt className="label-caps text-ink-tertiary">{term}</dt>
      <dd className="mt-2">{children}</dd>
    </div>
  );
}

function FairCard({ fair, next, today }: { fair: FairOut; next: boolean; today: string }) {
  const soon = countdown(fair, today);
  const running = soon === "Heute geöffnet";
  const hours = hourLines(fair.hours);
  return (
    <article
      aria-labelledby={`messe-${fair.id}`}
      className="grid gap-6 rounded-lg bg-surface p-6 sm:grid-cols-[11rem_minmax(0,1fr)] sm:gap-10 sm:p-8"
    >
      <FairDate fair={fair} />
      <div className="min-w-0">
        {next || soon ? (
          <p className={cn("label-caps", next ? "text-accent" : "text-ink-tertiary")}>
            {[next ? (running ? "Jetzt" : "Nächster Halt") : null, soon].filter(Boolean).join(" · ")}
          </p>
        ) : null}
        <h3 id={`messe-${fair.id}`} className="mt-2 text-[1.375rem] leading-7 hyphens-auto break-words sm:text-heading">
          {fair.name}
        </h3>
        <p className="mt-2 text-ink-secondary">{place(fair)}</p>

        {fair.booth || hours.length > 0 ? (
          <dl className="mt-6 grid gap-5 sm:grid-cols-2">
            {fair.booth ? (
              <Detail term="Unser Stand">
                <BoothSign>{fair.booth}</BoothSign>
              </Detail>
            ) : null}
            {hours.length > 0 ? (
              <Detail term="Geöffnet">
                {hours.map((line) => (
                  <span key={line} className="block text-small leading-6">
                    {line}
                  </span>
                ))}
              </Detail>
            ) : null}
          </dl>
        ) : null}

        {fair.note ? <p className="mt-5 text-small whitespace-pre-line text-ink-secondary">{fair.note}</p> : null}

        <div className="mt-6 flex flex-wrap items-center gap-x-6 gap-y-3">
          <Button asChild variant="secondary" size="sm">
            <a href={fairEventUrl(fair.id)} download>
              <CalendarIcon />
              In den Kalender
            </a>
          </Button>
          <a href={routeUrl(fair)} target="_blank" rel="noopener noreferrer" className={ACTION_LINK}>
            <RouteIcon />
            Route planen<span className="sr-only"> (OpenStreetMap, neues Fenster)</span>
          </a>
          {fair.website_url ? (
            <a href={fair.website_url} target="_blank" rel="noopener noreferrer" className={ACTION_LINK}>
              <ExternalIcon />
              Website der Messe<span className="sr-only"> (neues Fenster)</span>
            </a>
          ) : null}
        </div>
      </div>
    </article>
  );
}

/** The fairs still to come, the soonest first, as stops on a line. */
export function UpcomingFairs({ fairs, today }: { fairs: readonly FairOut[]; today: string }) {
  return (
    <ol className="space-y-6">
      {fairs.map((fair, index) => (
        <li key={fair.id} className="group relative pl-9 sm:pl-14">
          {/* The line to the next stop. */}
          <span
            aria-hidden="true"
            className="absolute top-11 -bottom-17 left-[7.5px] w-px bg-line-strong group-last:hidden"
          />
          <Station kind={index === 0 ? "next" : "later"} running={countdown(fair, today) === "Heute geöffnet"} />
          <FairCard fair={fair} next={index === 0} today={today} />
        </li>
      ))}
    </ol>
  );
}

/** The last fairs, the latest first: small, on a dashed line. */
export function PastFairs({ fairs }: { fairs: readonly FairOut[] }) {
  return (
    <ol className="space-y-5">
      {fairs.map((fair) => (
        <li key={fair.id} className="group relative pl-9 sm:pl-14">
          <span
            aria-hidden="true"
            className="absolute top-3 -bottom-8 left-[7.5px] border-l border-dashed border-line-strong group-last:hidden"
          />
          <Station kind="past" />
          <p className="grid gap-x-6 gap-y-1 sm:grid-cols-[13rem_minmax(0,1fr)]">
            <span className="text-small text-ink-tertiary tabular-nums">{fair.when}</span>
            <span className="text-ink-secondary">
              {fair.name}
              <span className="text-ink-tertiary"> · {fair.city}</span>
            </span>
          </p>
        </li>
      ))}
    </ol>
  );
}
