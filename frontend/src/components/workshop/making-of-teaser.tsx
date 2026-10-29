import Link from "next/link";

import { Button } from "@/components/ui/button";
import { hoursOf, totalsOf } from "@/lib/workshop/explosion";
import { PLACEHOLDER_MODEL } from "@/lib/workshop/placeholder-model";

const STEPS = [
  { title: "Konstruieren und zerlegen", text: "Das Vorbild am Rechner, in druckbare Teile geschnitten" },
  { title: "Drucken", text: "Teil für Teil auf den 12 Druckern der Werkstatt" },
  { title: "Nacharbeiten und zusammensetzen", text: "Schleifen, lackieren, beschriften, montieren" },
] as const;

/**
 * The start page's way into "So entsteht ein Modell": the three steps as numbered
 * positions on a drawing sheet. The figures of the model appear once it is a real one;
 * a placeholder's examples stay on its own page, marked as such.
 */
export function MakingOfTeaser() {
  const model = PLACEHOLDER_MODEL;
  const totals = totalsOf(model);
  return (
    <section aria-labelledby="so-entsteht" className="border-t border-line">
      <div className="mx-auto grid max-w-6xl items-center gap-12 px-5 py-16 sm:px-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:gap-20 lg:py-24">
        <div>
          <p className="label-caps text-ink-tertiary">Werkstatt</p>
          <h2 id="so-entsteht" className="mt-4 text-heading">
            So entsteht ein Modell
          </h2>
          <p className="mt-4 max-w-xl text-body-lg text-ink-secondary">
            Ein Fahrzeug, in seine Teile zerlegt und wieder zusammengesetzt: Scroll durch die Explosionszeichnung und
            sieh, wie viel Arbeit in einem einzigen Modell steckt.
          </p>
          {model.placeholder ? null : (
            <dl className="mt-8 flex flex-wrap gap-x-10 gap-y-3">
              {[
                [String(totals.parts), "Teile"],
                [String(hoursOf(totals.printMinutes)), "Stunden Druck"],
                [String(hoursOf(totals.handworkMinutes)), "Stunden Handarbeit"],
              ].map(([value, label]) => (
                <div key={label} className="grid">
                  <dt className="text-hint text-ink-tertiary">{label}</dt>
                  <dd className="order-first m-0 text-title font-extralight tabular-nums">{value}</dd>
                </div>
              ))}
            </dl>
          )}
          <Button asChild className="mt-8">
            <Link href="/so-entsteht-ein-modell">Zur Explosionszeichnung</Link>
          </Button>
        </div>
        <ol
          aria-label="Arbeitsschritte"
          className="m-0 grid list-none gap-0 rounded-lg bg-stage bg-[image:linear-gradient(var(--drawing-grid)_1px,transparent_1px),linear-gradient(90deg,var(--drawing-grid)_1px,transparent_1px)] bg-[size:16px_16px] bg-[position:-1px_-1px] p-6 sm:p-8"
        >
          {STEPS.map((step, index) => (
            <li
              key={step.title}
              className="group relative grid grid-cols-[1.75rem_minmax(0,1fr)] gap-x-4 pb-8 last:pb-0"
            >
              {/* The leader line down to the next position, as on a drawing. */}
              <span
                aria-hidden="true"
                className="absolute top-7 bottom-0 left-[13.5px] w-px bg-drawing-line group-last:hidden"
              />
              <span
                aria-hidden="true"
                className="relative grid size-7 place-items-center rounded-full border border-drawing-line bg-stage font-mono text-[0.75rem] text-accent"
              >
                {index + 1}
              </span>
              <div className="pt-0.5">
                <h3 className="text-body font-medium">{step.title}</h3>
                <p className="mt-1 text-small text-ink-secondary">{step.text}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
