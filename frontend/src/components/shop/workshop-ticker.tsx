import type { OrderOut } from "@/lib/api/generated/model";
import { formatClock, formatLongDate } from "@/lib/format";
import { cn } from "@/lib/utils";

const STEPS = ["Eingeplant", "Im Drucker", "Bauen und prüfen", "Verpacken"] as const;

/**
 * Werkstatt-Ticker (ADR 0034): for a paid order whose pieces are made for the customer,
 * where they stand in the workshop. The plates are planned as soon as the money is in;
 * when the first one is on the printer, the ticker says since when.
 */
export function WorkshopTicker({ order, className }: { order: OrderOut; className?: string }) {
  const madeToOrder = order.lead_time_min_weeks !== null && order.lead_time_min_weeks !== undefined;
  const started = order.making_started_at ? new Date(order.making_started_at) : null;
  if (order.status !== "paid" || (!madeToOrder && started === null)) {
    return null;
  }
  const current = started === null ? 0 : 1;
  return (
    <section aria-labelledby="werkstatt" className={cn("border border-line bg-surface", className)}>
      <div className="flex items-center gap-3 border-b border-line px-5 py-3">
        <span aria-hidden="true" className="relative flex size-2.5">
          <span className="absolute inset-0 animate-lamp-pulse rounded-full bg-accent" />
        </span>
        <h2 id="werkstatt" className="label-caps whitespace-nowrap text-ink-secondary">
          Werkstatt-Ticker
        </h2>
        <span className="ml-auto font-mono text-hint text-ink-tertiary max-sm:hidden">live aus der Werkstatt</span>
      </div>
      <div className="px-5 py-5">
        <p className="text-body-lg" aria-live="polite">
          {started ? (
            <>
              Seit {formatLongDate(started)}, {formatClock(started)} Uhr läuft der Drucker für dich.
            </>
          ) : (
            <>Deine Teile stehen auf dem Druckplan. Der Drucker legt bald los.</>
          )}
        </p>
        <ol className="mt-5 grid grid-cols-4 gap-1.5" aria-label="Fortschritt in der Werkstatt">
          {STEPS.map((step, index) => (
            <li key={step} aria-current={index === current ? "step" : undefined} className="min-w-0">
              <span
                aria-hidden="true"
                className={cn(
                  "block h-1.5",
                  index < current ? "bg-ink" : index === current ? "animate-lamp-pulse bg-accent" : "bg-line",
                )}
              />
              <span className={cn("mt-2 block text-hint", index <= current ? "text-ink" : "text-ink-tertiary")}>{step}</span>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
