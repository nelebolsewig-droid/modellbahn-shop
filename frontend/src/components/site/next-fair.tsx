import Link from "next/link";

import { Button } from "@/components/ui/button";
import { SignalLamp } from "@/components/ui/signal-lamp";
import type { FairOut } from "@/lib/api/generated/model";
import { countdown, fairEventUrl, place, todayInGermany } from "@/lib/site/fairs";

import { BoothSign, FairDate } from "./fair-timeline";

/** The start page's pointer to the next fair: date, place, booth and the way to all dates. */
export function NextFair({ fair }: { fair: FairOut }) {
  const soon = countdown(fair, todayInGermany());
  return (
    <section aria-labelledby="naechste-messe" className="border-t border-line">
      <div className="mx-auto max-w-6xl px-5 py-12 sm:px-8 lg:py-16">
        <div className="grid items-center gap-8 rounded-lg bg-surface p-6 sm:p-8 lg:grid-cols-[12rem_minmax(0,1fr)_auto] lg:gap-12">
          <FairDate fair={fair} size="medium" />
          <div className="min-w-0">
            <p className="flex items-center gap-2 label-caps text-accent">
              <SignalLamp color="blue" blinking={soon === "Heute geöffnet"} />
              {["Nächster Halt", soon].filter(Boolean).join(" · ")}
            </p>
            <h2 id="naechste-messe" className="mt-3 text-[1.375rem] leading-7 hyphens-auto break-words sm:text-heading">
              {fair.name}
            </h2>
            <p className="mt-2 text-ink-secondary">{place(fair)}</p>
            {fair.booth ? (
              <p className="mt-4">
                <BoothSign>{fair.booth}</BoothSign>
              </p>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2 lg:flex-col lg:items-stretch">
            <Button asChild size="sm">
              <Link href="/termine">Alle Termine</Link>
            </Button>
            <Button asChild variant="secondary" size="sm">
              <a href={fairEventUrl(fair.id)} download>
                In den Kalender
              </a>
            </Button>
          </div>
        </div>
      </div>
    </section>
  );
}
