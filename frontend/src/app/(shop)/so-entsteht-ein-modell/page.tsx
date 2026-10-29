import type { Metadata } from "next";
import Link from "next/link";

import { PageHeading } from "@/components/site/page-heading";
import { Button } from "@/components/ui/button";
import { ExplosionView } from "@/components/workshop/explosion-view";
import { PLACEHOLDER_MODEL } from "@/lib/workshop/placeholder-model";

export const metadata: Metadata = {
  title: "So entsteht ein Modell",
  description: "Ein Fahrzeugmodell in seine Teile zerlegt: wie viele Teile, Druckstunden und Handarbeit darin stecken.",
};

export default function MakingOfPage() {
  return (
    <>
      <div className="mx-auto max-w-6xl px-5 pt-12 pb-6 sm:px-8 lg:pt-20 lg:pb-10">
        <PageHeading caption="Werkstatt" title="So entsteht ein Modell">
          <p>
            Scroll weiter: Das Modell fährt in seine Teile auseinander, zeigt jedes mit seiner Nummer und setzt sich am
            Ende wieder zusammen. So siehst du, wie viel Konstruktion, Druckzeit und Handarbeit in einem einzigen Modell
            stecken.
          </p>
        </PageHeading>
      </div>

      <ExplosionView model={PLACEHOLDER_MODEL} />

      <section aria-labelledby="eigenes-modell" className="mt-16 border-t border-line lg:mt-24">
        <div className="mx-auto grid max-w-6xl gap-8 px-5 py-16 sm:px-8 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end lg:py-20">
          <div className="max-w-xl">
            <h2 id="eigenes-modell" className="text-heading">
              Dein Vorbild fehlt noch?
            </h2>
            <p className="mt-4 text-body-lg text-ink-secondary">
              Auf demselben Weg entstehen Sonderanfertigungen: vom Einzelstück bis zur Kleinserie.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Button asChild>
              <Link href="/sonderanfertigung">Zur Sonderanfertigung</Link>
            </Button>
            <Button asChild variant="secondary">
              <Link href="/katalog">Zum Katalog</Link>
            </Button>
          </div>
        </div>
      </section>
    </>
  );
}
