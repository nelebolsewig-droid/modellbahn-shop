import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";

import { PageHeading } from "@/components/site/page-heading";
import { Button } from "@/components/ui/button";
import { TextLink } from "@/components/ui/text-link";
import { SHOP_NAME } from "@/lib/config";
import { loadImprint, phoneHref } from "@/lib/site/imprint";

export const metadata: Metadata = {
  title: "Über uns",
  description: "Fahrzeugmodelle in Handarbeit und Kleinserie, seit 1992.",
};

const MILESTONES = [
  { year: "1992", text: "Die ersten Fahrzeugmodelle entstehen – vom Flugzeug bis zur Lokomotive." },
  { year: "1998", text: "Polystyrol, Polyurethan und Weißmetall werden unsere Werkstoffe." },
  { year: "Heute", text: "Dazu 3D-Druck und Lasercutting für Sonderanfertigungen nach deinen Wünschen." },
] as const;

const FACTS = [
  { term: "Fertigung", details: "Handarbeit, limitierte Auflagen" },
  { term: "Werkstoffe", details: "Polystyrol · Polyurethan · Weißmetall" },
  { term: "Schiene", details: "Spur 0 · H0 · TT · N" },
  { term: "Straße", details: "1:87 · 1:43, Vorbilder der 1930er bis 1980er" },
  { term: "Herkunft", details: "Hergestellt in Deutschland" },
] as const;

export default async function AboutPage() {
  await connection();
  const imprint = await loadImprint();

  return (
    <div className="mx-auto max-w-6xl px-5 py-12 sm:px-8 lg:py-20">
      <PageHeading caption="Werkstatt" title="Über uns">
        <p>
          Seit 1992 fertigt {SHOP_NAME} Fahrzeugmodelle für Sammler und Modellbau-Begeisterte – immer in limitierter
          Auflage und mit einem Blick fürs Detail, der bei Massenware verloren geht.
        </p>
      </PageHeading>

      {/* The workshop's history as a line with three stations. */}
      <ol aria-label="Stationen" className="mt-14 grid gap-8 sm:grid-cols-3 sm:gap-0 lg:mt-20">
        {MILESTONES.map((milestone, index) => (
          <li key={milestone.year} className="group relative pl-10 sm:pt-10 sm:pr-8 sm:pl-0">
            <span
              aria-hidden="true"
              className="absolute top-2 -bottom-8 left-[7.5px] w-px bg-line-strong group-last:hidden sm:top-[7.5px] sm:right-0 sm:bottom-auto sm:left-0 sm:h-px sm:w-auto sm:group-last:block"
            />
            <span
              aria-hidden="true"
              className={
                index === MILESTONES.length - 1
                  ? "absolute top-0 left-0 size-4 rounded-full border-2 border-accent bg-accent shadow-[0_0_0_5px_var(--accent-subtle)]"
                  : "absolute top-0 left-0 size-4 rounded-full border-2 border-ink bg-canvas"
              }
            />
            <p className="text-title font-extralight tabular-nums">{milestone.year}</p>
            <p className="mt-2 max-w-xs text-ink-secondary">{milestone.text}</p>
          </li>
        ))}
      </ol>

      <div className="mt-16 grid gap-12 lg:mt-24 lg:grid-cols-[minmax(0,1fr)_24rem] lg:gap-20">
        <div className="max-w-2xl space-y-10 text-body-lg leading-8 text-ink-secondary">
          <section aria-labelledby="handarbeit">
            <h2 id="handarbeit" className="text-heading text-ink">
              Sorgfalt statt Fließband
            </h2>
            <p className="mt-4">
              Jedes Modell entsteht bei uns in Handarbeit. Seit 1998 arbeiten wir hauptsächlich mit Polystyrol,
              Polyurethan und Weißmetall – hergestellt in Deutschland. Manche Modelle bauen wir erst, wenn du sie
              bestellst; wie lange das dauert, steht vorher am Artikel.
            </p>
          </section>
          <section aria-labelledby="sortiment">
            <h2 id="sortiment" className="text-heading text-ink">
              Vom Autokran bis zur Straßenbahn
            </h2>
            <p className="mt-4">
              Unser Sortiment reicht von Automodellen der 1930er- bis 1980er-Jahre in 1:87 und 1:43 über
              Schienenfahrzeuge in Spur 0, H0, TT und N bis zu Plastikbausätzen und Zubehör für Modellbahn und
              Modellauto. Und wenn es dein Modell noch nicht gibt: Wir fertigen es als{" "}
              <TextLink href="/sonderanfertigung">Sonderanfertigung</TextLink>.
            </p>
          </section>
          <section aria-labelledby="antrieb">
            <h2 id="antrieb" className="text-heading text-ink">
              Was uns antreibt
            </h2>
            <p className="mt-4">
              Derselbe Enthusiasmus, den du mitbringst: die Freude an präzise nachgebildeten Details, an Fahrzeugen
              mit Geschichte und an Handwerk, das man in der Hand spürt. Ob du schon lange sammelst oder gerade
              erst einsteigst – bei uns findest du Modelle, die mit Sorgfalt entstanden sind.
            </p>
          </section>
        </div>

        <aside className="space-y-6 self-start">
          <section aria-labelledby="steckbrief" className="rounded-lg bg-surface p-6 sm:p-8">
            <h2 id="steckbrief" className="label-caps text-ink-tertiary">
              Steckbrief
            </h2>
            <dl className="mt-5 divide-y divide-line">
              {FACTS.map((fact) => (
                <div key={fact.term} className="grid grid-cols-[6.5rem_minmax(0,1fr)] gap-4 py-3 first:pt-0 last:pb-0">
                  <dt className="text-small text-ink-tertiary">{fact.term}</dt>
                  <dd className="text-small text-ink">{fact.details}</dd>
                </div>
              ))}
            </dl>
          </section>
          <section aria-labelledby="kontakt" className="rounded-lg border border-line p-6 sm:p-8">
            <h2 id="kontakt" className="text-body font-medium">
              Sprich uns an
            </h2>
            <p className="mt-2 text-small text-ink-secondary">
              Per E-Mail, am Telefon oder persönlich am Messestand.
            </p>
            {imprint?.email ? (
              <p className="mt-4 text-small">
                <a href={`mailto:${imprint.email}`} className="break-all text-accent hover:underline">
                  {imprint.email}
                </a>
                {imprint.phone ? (
                  <>
                    <br />
                    <a href={phoneHref(imprint.phone)} className="text-accent hover:underline">
                      {imprint.phone}
                    </a>
                  </>
                ) : null}
              </p>
            ) : null}
            <Button asChild variant="secondary" size="sm" className="mt-5">
              <Link href="/termine">Zu den Messeterminen</Link>
            </Button>
          </section>
        </aside>
      </div>
    </div>
  );
}
