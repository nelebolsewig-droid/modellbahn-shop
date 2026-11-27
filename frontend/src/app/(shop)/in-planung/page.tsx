import type { Metadata } from "next";
import Link from "next/link";

import { PageHeading } from "@/components/site/page-heading";
import { Button } from "@/components/ui/button";
import { ROADMAP, ROADMAP_STAGES } from "@/lib/site/roadmap";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
  title: "Was ist in Planung",
  description: "Diese Modelle entstehen gerade in der Werkstatt: von der Idee über den Probedruck bis in den Shop.",
};

export default function RoadmapPage() {
  const order = ROADMAP_STAGES.map((stage) => stage.code);
  const entries = [...ROADMAP].sort((a, b) => order.indexOf(b.stage) - order.indexOf(a.stage));
  return (
    <>
      <div className="mx-auto max-w-6xl px-5 pt-12 pb-10 sm:px-8 lg:pt-20 lg:pb-16">
        <PageHeading caption="Vorschau" title="Was ist in Planung">
          <p>
            Ein Blick auf die Werkbank: Diese Modelle entstehen gerade. Vom ersten Entwurf bis zum fertigen Bausatz
            durchläuft jedes Modell vier Stationen.
          </p>
        </PageHeading>
      </div>

      {/* The four stations as a track, the stage of each model as a lit signal. */}
      <section aria-label="Stationen" className="border-t border-line bg-stage">
        <ol className="mx-auto grid max-w-6xl list-none gap-px p-0 px-5 py-12 sm:grid-cols-4 sm:px-8">
          {ROADMAP_STAGES.map((stage, index) => (
            <li key={stage.code} className="scroll-rise border-t-4 border-accent bg-surface p-5">
              <span className="font-mono text-hint text-ink-tertiary">{String(index + 1).padStart(2, "0")}</span>
              <p className="mt-1 font-medium">{stage.label}</p>
              <p className="mt-1 text-small text-ink-secondary">{stage.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="modelle" className="border-t border-line">
        <div className="mx-auto max-w-6xl px-5 py-16 sm:px-8 lg:py-24">
          <h2 id="modelle" className="sr-only">
            Geplante Modelle
          </h2>
          {entries.length === 0 ? (
            <div className="scroll-rise border border-line-strong bg-surface p-8 shadow-[8px_8px_0_var(--accent-subtle)] sm:p-12">
              <p className="label-caps text-accent">Gerade auf der Werkbank</p>
              <p className="mt-4 text-heading">Die nächsten Modelle verraten wir in Kürze.</p>
              <p className="mt-3 max-w-xl text-ink-secondary">
                Du hast ein Vorbild, das unbedingt dazugehört? Schreib uns: Viele unserer Modelle sind aus Wünschen
                entstanden.
              </p>
            </div>
          ) : (
            <ul className="grid list-none gap-6 p-0 md:grid-cols-2">
              {entries.map((entry) => {
                const reached = order.indexOf(entry.stage);
                return (
                  <li
                    key={entry.name}
                    className="scroll-rise border border-line-strong bg-surface p-6 shadow-[6px_6px_0_var(--accent-subtle)] sm:p-8"
                  >
                    <div className="flex flex-wrap items-baseline justify-between gap-3">
                      <h3 className="text-[1.35rem] leading-7">{entry.name}</h3>
                      {entry.when ? <span className="text-small text-ink-tertiary">{entry.when}</span> : null}
                    </div>
                    <p className="mt-2 text-small text-ink-secondary">{entry.scales.join(" · ")}</p>
                    {entry.note ? <p className="mt-3 text-ink-secondary">{entry.note}</p> : null}
                    <ol aria-label="Stand" className="mt-6 grid list-none grid-cols-4 gap-1 p-0">
                      {ROADMAP_STAGES.map((stage, index) => (
                        <li key={stage.code} className="text-hint">
                          <span
                            aria-hidden="true"
                            className={cn("block h-1.5", index <= reached ? "bg-accent" : "bg-sunken")}
                          />
                          <span
                            className={cn(
                              "mt-1.5 block",
                              index === reached ? "font-medium text-ink" : "text-ink-tertiary",
                            )}
                          >
                            {stage.label}
                            {index === reached ? <span className="sr-only"> (aktuell)</span> : null}
                          </span>
                        </li>
                      ))}
                    </ol>
                  </li>
                );
              })}
            </ul>
          )}
          <div className="mt-12 flex flex-wrap gap-3">
            <Button asChild>
              <Link href="/sonderanfertigung">Wunschmodell vorschlagen</Link>
            </Button>
            <Button asChild variant="secondary">
              <Link href="/katalog">Zu den Modellen</Link>
            </Button>
          </div>
        </div>
      </section>
    </>
  );
}
