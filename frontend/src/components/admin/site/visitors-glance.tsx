"use client";

import { useListVisits } from "@/lib/api/generated/admin-site/admin-site";
import type { VisitDayOut } from "@/lib/api/generated/model";
import { errorMessage } from "@/lib/i18n/problems";
import { cn } from "@/lib/utils";

const DAYS = 30;

/**
 * Besucher: today's visitors big, beside it yesterday and the 30-day average, below the
 * last 30 days as bars (today's in orange). Counted without cookies (ADR 0043).
 */
export function VisitorsGlance() {
  const visits = useListVisits(
    { days: DAYS },
    { query: { refetchInterval: 60_000 } },
  );
  const days = visits.data?.days ?? [];
  const today = days.at(-1);
  const yesterday = days.at(-2);
  const average =
    days.length > 0
      ? Math.round(
          days.reduce((sum, day) => sum + day.visitors, 0) / days.length,
        )
      : 0;
  const peak = Math.max(1, ...days.map((day) => day.visitors));

  return (
    <section className="bg-surface px-5 py-5 sm:px-6">
      <div className="flex items-baseline justify-between gap-4">
        <h2 className="text-heading">Besucher</h2>
        <span className="label-caps text-ink-secondary">ohne Cookies</span>
      </div>
      {visits.isError ? (
        <p role="alert" className="mt-4 text-small text-danger">
          {errorMessage(visits.error)}
        </p>
      ) : (
        <>
          <dl className="mt-3 grid grid-cols-[auto_1fr_1fr] items-end gap-x-5">
            <div>
              <dt className="label-caps text-ink-secondary">Heute</dt>
              <dd className="font-display text-[3rem] leading-[0.85] font-extrabold tracking-[-0.05em] tabular-nums">
                {today ? today.visitors : "–"}
              </dd>
            </div>
            <Figure label="Gestern" value={yesterday?.visitors} />
            <Figure
              label="Ø 30 Tage"
              value={visits.data ? average : undefined}
            />
          </dl>
          <p className="mt-2 text-small text-ink-secondary">
            {today
              ? `${today.page_views} Seitenaufrufe heute`
              : "Wird geladen …"}
          </p>
          <ol
            aria-label="Besucher der letzten 30 Tage"
            className="mt-4 flex h-16 items-end gap-[3px] [perspective:400px]"
          >
            {days.map((day, index) => (
              <Bar
                key={day.day}
                day={day}
                height={day.visitors / peak}
                current={index === days.length - 1}
              />
            ))}
          </ol>
        </>
      )}
    </section>
  );
}

function Figure({
  label,
  value,
}: {
  label: string;
  value: number | undefined;
}) {
  return (
    <div>
      <dt className="label-caps text-ink-secondary">{label}</dt>
      <dd className="font-mono text-[1.375rem] font-medium tabular-nums">
        {value ?? "–"}
      </dd>
    </div>
  );
}

function Bar({
  day,
  height,
  current,
}: {
  day: VisitDayOut;
  height: number;
  current: boolean;
}) {
  const label = `${new Date(`${day.day}T12:00:00`).toLocaleDateString("de-DE", { day: "numeric", month: "short" })}: ${day.visitors} Besucher`;
  return (
    <li title={label} className="flex h-full flex-1 items-end">
      <span className="sr-only">{label}</span>
      <span
        aria-hidden="true"
        className={cn(
          "block w-full origin-bottom shadow-[inset_0_1px_0_rgb(255_255_255/0.35),2px_0_0_rgb(0_0_0/0.08)] transition-transform duration-200 ease-out hover:[transform:rotateX(-8deg)_scaleY(1.06)] motion-reduce:transition-none",
          current ? "bg-action" : "bg-sunken hover:bg-accent-subtle",
        )}
        style={{ height: `${Math.max(4, Math.round(height * 100))}%` }}
      />
    </li>
  );
}
