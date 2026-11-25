import type { Metadata } from "next";
import Link from "next/link";

import { PageHeading } from "@/components/site/page-heading";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = {
  title: "Der Weg zum perfekten Modell",
  description:
    "Bauanleitung für Resin-Bausätze: Stützen entfernen, das richtige Werkzeug, Kleben, Bemalen und die Teile richtig lagern.",
};

const TOOLS = [
  { name: "Bündiger Seitenschneider", use: "Stützen knapp am Teil abknipsen" },
  { name: "Bastelmesser oder Skalpell", use: "Ansatzpunkte sauber abtragen" },
  {
    name: "Schleifpapier 400 bis 1000, Feilen",
    use: "Nass schleifen, bis nichts mehr übersteht",
  },
  { name: "Spitze Pinzette", use: "Kleinteile greifen und ansetzen" },
  {
    name: "Sekundenkleber als Gel",
    use: "Für fast alle Verbindungen, sparsam",
  },
  { name: "Zahnstocher", use: "Kleber punktgenau auftragen" },
  {
    name: "Isopropanol oder Spülmittel",
    use: "Teile vor dem Grundieren entfetten",
  },
  {
    name: "Handschuhe und Staubmaske",
    use: "Beim Schleifen: Resinstaub nicht einatmen",
  },
] as const;

const STEPS = [
  {
    title: "Auspacken und prüfen",
    text: "Leg alle Teile auf eine helle Unterlage und vergleiche sie mit der Teileliste. Die Nummern auf den Stützen helfen beim Zuordnen. Fehlt etwas oder ist ein Teil gebrochen, melde dich: Wir drucken es nach.",
  },
  {
    title: "Stützen entfernen",
    text: "Knipse die Stützen mit dem Seitenschneider ein bis zwei Millimeter vor dem Teil ab, nie direkt am Teil und nie abbrechen. Resin ist hart und kann an dünnen Stellen ausreißen. Kurz in warmes Wasser gelegt, wird es etwas weicher und schneidet sich leichter.",
  },
  {
    title: "Verschleifen und entgraten",
    text: "Die Reste der Stützen trägst du mit dem Messer flach ab und schleifst nass nach, erst grob mit 400er, dann fein mit 800er bis 1000er Papier. Nass schleifen bindet den Staub. Kleine Löcher füllst du mit Spachtel oder einem Tropfen Sekundenkleber.",
  },
  {
    title: "Reinigen",
    text: "Wasche die Teile in lauwarmem Wasser mit etwas Spülmittel oder wisch sie mit Isopropanol ab. Fett von den Fingern lässt sonst Farbe und Kleber nicht halten. Danach vollständig trocknen lassen.",
  },
  {
    title: "Trocken anpassen, dann kleben",
    text: "Setze jedes Teil erst ohne Kleber an. Passt alles, kommt Sekundenkleber als Gel mit dem Zahnstocher in kleinen Punkten auf die Klebefläche. Plastikkleber löst Resin nicht an und hält deshalb nicht. Für große, tragende Teile eignet sich 2K-Epoxidkleber.",
  },
  {
    title: "Grundieren und bemalen",
    text: "Eine dünne Grundierung aus der Spraydose oder dem Airbrush zeigt letzte Kratzer und gibt der Farbe Halt. Danach mit Acryl- oder Kunstharzfarben bemalen, in mehreren dünnen Schichten statt einer dicken.",
  },
  {
    title: "Richtig lagern",
    text: "Unverbaute Teile und fertige Modelle mögen es dunkel, trocken und nicht zu warm. Sonnenlicht macht Resin mit der Zeit spröde, Hitze kann dünne Teile verziehen. Lagere Kleinteile flach in einem Beutel oder auf Schaumstoff, damit nichts bricht oder verloren geht.",
  },
] as const;

export default function GuidePage() {
  return (
    <>
      <div className="mx-auto max-w-6xl px-5 pt-12 pb-10 sm:px-8 lg:pt-20 lg:pb-16">
        <PageHeading caption="Bauanleitung" title="Der Weg zum perfekten Modell">
          <p>
            Ein Bausatz von uns ist im Resin-Druck entstanden. Mit ein wenig Werkzeug und Geduld wird daraus ein Modell,
            das aussieht wie gekauft und doch dein eigenes ist. So gehst du vor.
          </p>
        </PageHeading>
      </div>

      <section aria-labelledby="werkzeug" className="border-t border-line bg-stage">
        <div className="mx-auto max-w-6xl px-5 py-16 sm:px-8 lg:py-20">
          <h2 id="werkzeug" className="scroll-rise text-heading">
            Empfohlenes Werkzeug
          </h2>
          <ul className="mt-10 grid gap-px border border-line-strong bg-line-strong sm:grid-cols-2 lg:grid-cols-4">
            {TOOLS.map((tool) => (
              <li key={tool.name} className="scroll-rise bg-surface p-5">
                <p className="font-medium">{tool.name}</p>
                <p className="mt-1 text-small text-ink-secondary">{tool.use}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section aria-labelledby="schritte" className="border-t border-line">
        <div className="mx-auto max-w-6xl px-5 py-16 sm:px-8 lg:py-24">
          <h2 id="schritte" className="scroll-rise text-heading">
            Schritt für Schritt
          </h2>
          <ol className="mt-12 grid list-none gap-6 p-0 lg:grid-cols-2">
            {STEPS.map((step, index) => (
              <li
                key={step.title}
                className="scroll-rise relative border border-line-strong bg-surface p-6 shadow-[6px_6px_0_var(--accent-subtle)] transition-transform duration-200 hover:-translate-y-1 hover:shadow-[10px_10px_0_var(--accent-subtle)] sm:p-8"
              >
                <span
                  aria-hidden="true"
                  className="font-display text-[3.5rem] leading-none font-extrabold text-accent tabular-nums"
                >
                  {String(index + 1).padStart(2, "0")}
                </span>
                <h3 className="mt-4 text-[1.35rem] leading-7">{step.title}</h3>
                <p className="mt-3 text-ink-secondary">{step.text}</p>
              </li>
            ))}
          </ol>
          <p className="scroll-rise mt-12 max-w-2xl border-l-4 border-accent pl-5 text-small text-ink-secondary">
            Sicherheit: Schleife möglichst nass und mit Staubmaske, arbeite bei Kleber und Farbe am offenen Fenster und
            halte Kleinteile von Kindern fern.
          </p>
        </div>
      </section>

      <section aria-labelledby="motto" className="border-t border-line bg-stage">
        <div className="mx-auto grid max-w-6xl gap-8 px-5 py-16 sm:px-8 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end lg:py-20">
          <p id="motto" className="scroll-rise font-display text-[2rem] leading-tight font-extrabold sm:text-[2.75rem]">
            Modellbau ist mehr als ein Hobby.
            <span className="slogan-depth block">Baue, was du liebst.</span>
          </p>
          <div className="flex flex-wrap gap-3">
            <Button asChild>
              <Link href="/katalog">Zu den Bausätzen</Link>
            </Button>
            <Button asChild variant="secondary">
              <Link href="/in-planung">Was ist in Planung?</Link>
            </Button>
          </div>
        </div>
      </section>
    </>
  );
}
