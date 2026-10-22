import { HomeActions } from "@/components/site/home-actions";
import { TrackPlan } from "@/components/site/track-plan";

// What the concept plans for the next steps (docs/KONZEPT.md, "Fahrplan"); the
// start page says honestly that none of it is open yet.
const COMING = [
  {
    title: "Katalog",
    text: "Gebäude, Bausätze und Kleinteile in H0 und N, jede Ausführung mit Maßen und Fotos.",
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
      <section className="mx-auto grid max-w-6xl items-center gap-12 px-5 pt-12 pb-16 sm:px-8 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] lg:gap-16 lg:pt-20 lg:pb-24">
        <div>
          <p className="label-caps flex items-center gap-2 text-ink-muted">
            <span className="size-2 rounded-full bg-accent" aria-hidden="true" />
            Gleis 1 · Im Aufbau
          </p>
          <h1 className="mt-5 text-5xl sm:text-6xl lg:text-7xl">
            Hier entsteht ein Shop für 3D-gedruckte Modellbahn-Artikel.
          </h1>
          <p className="mt-6 max-w-xl text-lg leading-8 text-ink-muted">
            Konstruiert, gedruckt und geprüft in unserer eigenen Werkstatt. Der Katalog folgt –
            ein Kundenkonto kannst du dir schon heute anlegen.
          </p>
          <HomeActions />
        </div>
        <TrackPlan className="mx-auto max-w-xl lg:max-w-none" />
      </section>

      <section aria-labelledby="was-hier-entsteht" className="bg-surface-sunken">
        <div className="mx-auto max-w-6xl px-5 py-14 sm:px-8 lg:py-20">
          <h2 id="was-hier-entsteht" className="text-3xl sm:text-4xl">
            Was hier entsteht
          </h2>
          <ol className="mt-10 grid gap-px overflow-hidden rounded-md bg-line-strong rule border-line-strong sm:grid-cols-3">
            {COMING.map((item, index) => (
              <li key={item.title} className="bg-surface-raised p-6 sm:p-7">
                <span className="font-mono text-sm text-accent-text" aria-hidden="true">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <h3 className="mt-3 text-2xl">{item.title}</h3>
                <p className="mt-3 leading-7 text-ink-muted">{item.text}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>
    </>
  );
}
