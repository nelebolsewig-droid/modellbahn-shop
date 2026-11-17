import type { Metadata } from "next";
import Link from "next/link";

import { PageHeading } from "@/components/site/page-heading";
import { Button } from "@/components/ui/button";
import { ExplosionView } from "@/components/workshop/explosion-view";
import { MotionStage } from "@/components/workshop/motion-stage";
import { EDK6_MODEL } from "@/lib/workshop/edk6-model";

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

      <ExplosionView model={EDK6_MODEL} />

      <section aria-labelledby="in-bewegung" className="mx-auto mt-16 max-w-6xl px-5 sm:px-8 lg:mt-24">
        <p className="label-caps label-tick text-ink-tertiary">Fertig montiert</p>
        <h2 id="in-bewegung" className="mt-4 text-title font-semibold tracking-[-0.03em]">
          Der Kran in <span className="text-spectrum">Bewegung</span>
        </h2>
        <p className="mt-4 max-w-2xl text-body-lg text-ink-secondary">
          Lackiert in Bahnfarben, mit mattem Metall und glänzendem Lack: So steht, fährt und bremst der EDK 6. Der
          Oberwagen dreht auf seinem Drehkranz, die Seilklappe schwingt auf.
        </p>
        <div className="mt-8">
          <MotionStage model={EDK6_MODEL} />
        </div>
      </section>

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
