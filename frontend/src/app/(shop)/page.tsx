import { HomeActions } from "@/components/site/home-actions";
import { SignalBoxDrawing } from "@/components/site/signal-box-drawing";
import { SpecLine } from "@/components/ui/spec-line";

// The gauges the shop will serve, with scale and track gauge.
const GAUGES = [
  { name: "H0", spec: ["1:87", "16,5 mm"] },
  { name: "TT", spec: ["1:120", "12 mm"] },
  { name: "N", spec: ["1:160", "9 mm"] },
] as const;

// What the concept plans for the next steps (docs/KONZEPT.md, "Fahrplan"); the
// start page says honestly that none of it is open yet.
const COMING = [
  {
    title: "Katalog",
    text: "Gebäude, Bausätze und Kleinteile in H0, TT und N, jede Ausführung mit Maßen und Fotos.",
  },
  {
    title: "Bausätze mit Stückliste",
    text: "Du siehst vorher, welche Teile in der Schachtel liegen und was du selbst ergänzt.",
  },
  {
    title: "Bestellen",
    text: "Mit Kundenkonto oder als Gast. Gastbestellungen landen später in deinem Konto, sobald deine E-Mail-Adresse bestätigt ist.",
  },
] as const;

export default function HomePage() {
  return (
    <>
      <section className="mx-auto grid max-w-6xl items-center gap-14 px-5 pt-14 pb-20 sm:px-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:gap-20 lg:pt-24 lg:pb-32">
        <div>
          <p className="label-caps text-ink-tertiary">Gleis 1 · Im Aufbau</p>
          <h1 className="mt-5 text-title sm:text-display">
            Hier entsteht ein Shop für 3D-gedruckte Modellbahn-Artikel.
          </h1>
          <p className="mt-6 max-w-xl text-body-lg text-ink-secondary">
            Konstruiert, gedruckt und geprüft in unserer eigenen Werkstatt. Der Katalog folgt; ein
            Kundenkonto kannst du dir schon heute anlegen.
          </p>
          <HomeActions />
        </div>
        <SignalBoxDrawing className="mx-auto w-full max-w-xl lg:max-w-none" />
      </section>

      <section aria-labelledby="spurweiten" className="border-t border-line">
        <div className="mx-auto max-w-6xl px-5 py-16 sm:px-8 lg:py-24">
          <h2 id="spurweiten" className="text-heading">
            Für H0, TT und N
          </h2>
          <ul className="mt-10 grid gap-px overflow-hidden rounded-md bg-line sm:grid-cols-3">
            {GAUGES.map((gauge) => (
              <li key={gauge.name} className="bg-canvas py-6 sm:px-6 sm:first:pl-0">
                <p className="text-title">{gauge.name}</p>
                <SpecLine values={gauge.spec} size="small" className="mt-2" />
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section aria-labelledby="was-hier-entsteht" className="bg-stage">
        <div className="mx-auto max-w-6xl px-5 py-16 sm:px-8 lg:py-24">
          <h2 id="was-hier-entsteht" className="text-heading">
            Was hier entsteht
          </h2>
          <ul className="mt-10 grid gap-10 sm:grid-cols-3 sm:gap-12">
            {COMING.map((item) => (
              <li key={item.title} className="border-t border-line-strong pt-6">
                <h3 className="text-[1.25rem] leading-7 font-normal tracking-[-0.01em]">{item.title}</h3>
                <p className="mt-3 text-ink-secondary">{item.text}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </>
  );
}
