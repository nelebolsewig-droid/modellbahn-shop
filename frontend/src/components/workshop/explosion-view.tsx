"use client";

import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
  type RefObject,
} from "react";

import { cn } from "@/lib/utils";
import {
  explosionAt,
  formatDuration,
  hoursOf,
  phaseAt,
  totalsOf,
  type ExplosionModel,
  type Phase,
} from "@/lib/workshop/explosion";

// three.js loads only once the drawing comes near the screen.
const ExplosionScene = lazy(() => import("./explosion-scene"));

const STEPS = [
  {
    short: "Zerlegen",
    title: "Konstruieren und zerlegen",
    text: "Am Rechner wird das Vorbild nachgebaut und in Teile geschnitten, die sich sauber drucken lassen.",
  },
  {
    short: "Drucken",
    title: "Drucken",
    text: "Jedes Teil läuft einzeln über einen der 12 Drucker der Werkstatt, Schicht für Schicht.",
  },
  {
    short: "Zusammensetzen",
    title: "Nacharbeiten und zusammensetzen",
    text: "Stützen entfernen, schleifen, grundieren, lackieren, beschriften und alles montieren.",
  },
] as const;

const REDUCED_MOTION = "(prefers-reduced-motion: reduce)";

function subscribeToMotion(onChange: () => void): () => void {
  const query = window.matchMedia(REDUCED_MOTION);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

/** Whether the visitor asked for less motion; false while rendering on the server. */
function useReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribeToMotion,
    () => window.matchMedia(REDUCED_MOTION).matches,
    () => false,
  );
}

/** True once the element comes within a screen of the viewport. */
function useNearViewport(ref: RefObject<HTMLElement | null>): boolean {
  const [near, setNear] = useState(false);
  useEffect(() => {
    const element = ref.current;
    if (!element || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setNear(true);
          observer.disconnect();
        }
      },
      { rootMargin: "100% 0px" },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);
  return near;
}

/**
 * A model taken apart and put back together as the visitor scrolls: the drawing stays in
 * place while the page moves past, the process steps follow along, and the parts list
 * lights up the part under the pointer. With reduced motion it stands still, taken apart.
 */
export function ExplosionView({ model }: { model: ExplosionModel }) {
  const reducedMotion = useReducedMotion();
  const trackRef = useRef<HTMLElement>(null);
  const explosion = useRef(0);
  const [percent, setPercent] = useState(0);
  const [phase, setPhase] = useState<Phase>(0);
  const [manual, setManual] = useState(false);
  const [spinning, setSpinning] = useState(true);
  const [highlighted, setHighlighted] = useState<number | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const near = useNearViewport(trackRef);
  const onUnavailable = useCallback(() => setUnavailable(true), []);

  // The scroll position drives the explosion until the slider takes over; scrolling hands it back.
  useEffect(() => {
    if (reducedMotion) {
      // Standing still, taken apart, unless the slider moved it.
      if (!manual) explosion.current = 1;
      return;
    }
    let frame = 0;
    const follow = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const track = trackRef.current;
        if (!track) return;
        const span = track.offsetHeight - window.innerHeight;
        const progress = span > 0 ? Math.min(1, Math.max(0, -track.getBoundingClientRect().top / span)) : 0;
        explosion.current = explosionAt(progress);
        setPercent(Math.round(explosion.current * 100));
        setPhase(phaseAt(progress));
      });
    };
    const onScroll = () => {
      setManual(false);
      follow();
    };
    if (!manual) follow();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", follow);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", follow);
    };
  }, [reducedMotion, manual]);

  const totals = totalsOf(model);
  const resting = reducedMotion && !manual;
  const shownPercent = resting ? 100 : percent;
  const shownPhase: Phase = resting ? 1 : phase;
  const side = (
    <ProcessAndParts model={model} phase={shownPhase} highlighted={highlighted} onHighlight={setHighlighted} />
  );

  return (
    <>
      <section
        ref={trackRef}
        aria-label={`Explosionszeichnung: ${model.name}`}
        className={cn("relative", reducedMotion ? "h-auto" : "h-[300svh] max-lg:h-[260svh]")}
      >
        <div
          className={cn(
            "mx-auto grid max-w-6xl gap-6 px-5 sm:px-8 lg:grid-cols-[minmax(0,1fr)_22rem]",
            reducedMotion ? "h-[min(46rem,90svh)] py-4" : "sticky top-0 h-svh py-4 max-lg:h-[88svh]",
          )}
        >
          <div className="grid min-h-0 min-w-0 grid-rows-[minmax(0,1fr)_auto] gap-3 max-lg:grid-rows-[minmax(0,1fr)_auto_auto]">
            <div
              className={cn(
                "relative min-h-0 overflow-hidden rounded-lg bg-stage shadow-[inset_0_0_0_1px_var(--line)]",
                "bg-[image:linear-gradient(var(--drawing-grid)_1px,transparent_1px),linear-gradient(90deg,var(--drawing-grid)_1px,transparent_1px)]",
                "bg-[size:16px_16px] bg-[position:-1px_-1px]",
              )}
            >
              {near && !unavailable ? (
                <Suspense fallback={<StageNote>Zeichnung wird geladen …</StageNote>}>
                  <ExplosionScene
                    model={model}
                    explosion={explosion}
                    highlighted={highlighted}
                    onHighlight={setHighlighted}
                    spinning={spinning && !reducedMotion}
                    onUnavailable={onUnavailable}
                  />
                </Suspense>
              ) : null}
              {unavailable ? (
                <StageNote>Die 3D-Ansicht braucht WebGL. Die Stückliste zeigt alle Teile.</StageNote>
              ) : null}
              <ol
                aria-hidden="true"
                className="pointer-events-none absolute top-3.5 left-4 flex flex-wrap gap-1.5 font-mono text-hint"
              >
                {STEPS.map((step, index) => (
                  <li
                    key={step.short}
                    className={cn(
                      "rounded-full border px-2.5 py-0.5 transition-colors duration-150 ease-out",
                      index === shownPhase
                        ? "border-selected bg-selected text-on-selected"
                        : "border-line-strong bg-stage text-ink-tertiary",
                    )}
                  >
                    {index + 1} {step.short}
                  </li>
                ))}
              </ol>
              <dl className="pointer-events-none absolute right-4 bottom-4 hidden grid-cols-[auto_auto] border border-drawing-line bg-stage font-mono text-[0.6875rem] leading-4 sm:grid">
                {[
                  ["Benennung", model.placeholder ? `${model.name}, Platzhalter` : model.name],
                  ["Maßstab", model.scale],
                  ["Ansicht", "Explosionsdarstellung"],
                  ["Blatt", "1 / 1"],
                ].map(([term, value], index, rows) => (
                  <div key={term} className="contents">
                    <dt
                      className={cn(
                        "border-r border-drawing-helper px-2 py-1 text-ink-secondary",
                        index < rows.length - 1 && "border-b",
                      )}
                    >
                      {term}
                    </dt>
                    <dd
                      className={cn(
                        "m-0 px-2 py-1 text-ink",
                        index < rows.length - 1 && "border-b border-drawing-helper",
                      )}
                    >
                      {value}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
            <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
              <div className="flex min-w-0 flex-[1_1_16rem] items-center gap-3">
                <label htmlFor="explosion" className="label-caps text-ink-tertiary">
                  Zerlegt
                </label>
                <input
                  id="explosion"
                  type="range"
                  min={0}
                  max={100}
                  step={1}
                  value={shownPercent}
                  onChange={(event) => {
                    setManual(true);
                    explosion.current = Number(event.target.value) / 100;
                    setPercent(Number(event.target.value));
                    setPhase(explosion.current < 0.5 ? 0 : 1);
                  }}
                  className="min-w-0 flex-1 accent-accent"
                />
                <output
                  htmlFor="explosion"
                  className="min-w-[4ch] text-right font-mono text-hint text-ink-secondary tabular-nums"
                >
                  {shownPercent} %
                </output>
              </div>
              {!reducedMotion && !unavailable ? (
                <button
                  type="button"
                  onClick={() => setSpinning((value) => !value)}
                  className="h-9 rounded-full border border-line-control bg-surface px-4 text-small hover:bg-stage"
                >
                  {spinning ? "Drehung anhalten" : "Drehung starten"}
                </button>
              ) : null}
            </div>
            {/* On phones the steps stand below the drawing; the list follows after the track. */}
            <p className="m-0 min-h-[4.5rem] text-small text-ink-secondary lg:hidden">
              <span className="block font-medium text-ink">
                {shownPhase + 1} · {STEPS[shownPhase].title}
              </span>
              {STEPS[shownPhase].text}
            </p>
          </div>
          <aside className="hidden min-h-0 overflow-y-auto pr-1 lg:block">{side}</aside>
        </div>
      </section>
      <div className="mx-auto max-w-6xl px-5 pt-8 sm:px-8 lg:hidden">{side}</div>
      <p className="sr-only">
        {model.name}: {totals.parts} Teile, rund {hoursOf(totals.printMinutes)} Stunden Druck und{" "}
        {hoursOf(totals.handworkMinutes)} Stunden Handarbeit.
      </p>
    </>
  );
}

function StageNote({ children }: { children: ReactNode }) {
  return (
    <p className="absolute inset-0 m-0 grid place-items-center p-6 text-center text-small text-ink-secondary">
      {children}
    </p>
  );
}

type ProcessAndPartsProps = {
  model: ExplosionModel;
  phase: Phase;
  highlighted: number | null;
  onHighlight: (position: number | null) => void;
};

function ProcessAndParts({ model, phase, highlighted, onHighlight }: ProcessAndPartsProps) {
  const totals = totalsOf(model);
  return (
    <div className="grid content-start gap-8">
      <div>
        <h2 className="text-[1.375rem] leading-[1.875rem] font-normal tracking-[-0.01em]">So entsteht es</h2>
        <ol className="mt-3 grid gap-3.5">
          {STEPS.map((step, index) => (
            <li
              key={step.title}
              aria-current={index === phase ? "step" : undefined}
              className={cn(
                "grid grid-cols-[1.75rem_minmax(0,1fr)] gap-x-3 transition-colors duration-150 ease-out",
                index === phase ? "text-ink" : "text-ink-tertiary",
              )}
            >
              <span
                aria-hidden="true"
                className={cn(
                  "row-span-2 grid size-7 place-items-center rounded-full border font-mono text-[0.75rem]",
                  index === phase ? "border-selected bg-selected text-on-selected" : "border-line-strong",
                )}
              >
                {index + 1}
              </span>
              <strong className="text-[0.9375rem] leading-7 font-medium">{step.title}</strong>
              <p className="m-0 text-small">{step.text}</p>
            </li>
          ))}
        </ol>
      </div>
      <dl className="m-0 flex flex-wrap gap-x-6 gap-y-2">
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
      <div>
        <h2 className="text-[1.375rem] leading-[1.875rem] font-normal tracking-[-0.01em]">Stückliste</h2>
        <table className="mt-2 w-full border-collapse text-hint tabular-nums">
          <thead>
            <tr className="border-b border-line-strong text-left">
              <th scope="col" className="label-caps px-1.5 pb-1.5 font-medium text-ink-tertiary">
                Pos.
              </th>
              <th scope="col" className="label-caps px-1.5 pb-1.5 font-medium text-ink-tertiary">
                Benennung
              </th>
              <th scope="col" className="label-caps px-1.5 pb-1.5 text-right font-medium text-ink-tertiary">
                Stück
              </th>
              <th scope="col" className="label-caps px-1.5 pb-1.5 text-right font-medium text-ink-tertiary">
                Druck
              </th>
            </tr>
          </thead>
          <tbody>
            {model.parts.map((part) => (
              <tr
                key={part.position}
                onMouseEnter={() => onHighlight(part.position)}
                onMouseLeave={() => onHighlight(null)}
                className={cn(
                  "border-b border-line transition-colors duration-150 ease-out",
                  highlighted === part.position && "bg-accent-subtle",
                )}
              >
                <td className="px-1.5 py-2 font-mono text-accent">{part.position}</td>
                <td className="px-1.5 py-2">{part.name}</td>
                <td className="px-1.5 py-2 text-right">{part.count}</td>
                <td className="px-1.5 py-2 text-right whitespace-nowrap">{formatDuration(part.printMinutes)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="font-medium">
              <td className="px-1.5 pt-2.5" />
              <td className="px-1.5 pt-2.5">Summe</td>
              <td className="px-1.5 pt-2.5 text-right">{totals.parts}</td>
              <td className="px-1.5 pt-2.5 text-right whitespace-nowrap">{formatDuration(totals.printMinutes)}</td>
            </tr>
          </tfoot>
        </table>
        {model.placeholder ? (
          <p className="mt-3 rounded-sm bg-warning-subtle px-3 py-2 text-hint text-warning">
            Platzhalter: Dieses Fahrzeug ist nachgebaut, Teile und Zeiten sind Beispielwerte. Bald zeigen wir hier ein
            Modell aus der Werkstatt.
          </p>
        ) : null}
      </div>
    </div>
  );
}
