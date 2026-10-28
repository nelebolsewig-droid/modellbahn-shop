import type { Metadata } from "next";
import { connection } from "next/server";

import { CalendarSubscription } from "@/components/site/calendar-subscription";
import { FairNewsForm } from "@/components/site/fair-news-form";
import { PastFairs, UpcomingFairs } from "@/components/site/fair-timeline";
import { PageHeading } from "@/components/site/page-heading";
import { Alert } from "@/components/ui/alert";
import type { FairCalendarOut } from "@/lib/api/generated/model";
import { fetchStore } from "@/lib/api/server";
import { todayInGermany } from "@/lib/site/fairs";

export const metadata: Metadata = {
  title: "Termine",
  description: "Auf diesen Messen und Ausstellungen kannst du unsere Modelle in die Hand nehmen.",
};

/** The calendar; null while the API is unreachable (the page still offers the sign-up). */
async function loadCalendar(): Promise<FairCalendarOut | null> {
  try {
    return await fetchStore<FairCalendarOut>("/fairs");
  } catch {
    return null;
  }
}

export default async function FairsPage() {
  // Rendered per request: "Nächster Halt" and the countdown depend on today.
  await connection();
  const calendar = await loadCalendar();
  const today = todayInGermany();

  return (
    <div className="mx-auto max-w-6xl px-5 py-12 sm:px-8 lg:py-20">
      <PageHeading caption="Messen und Ausstellungen" title="Termine">
        <p>
          Hier stellen wir aus. Komm vorbei, nimm die Modelle in die Hand und erzähl uns, welches Fahrzeug dir
          noch fehlt.
        </p>
      </PageHeading>

      <div className="mt-12 grid items-start gap-12 lg:mt-16 lg:grid-cols-[minmax(0,1fr)_22rem] lg:gap-16">
        <div>
          <section aria-labelledby="kommende-messen">
            <h2 id="kommende-messen" className="sr-only">
              Kommende Messen
            </h2>
            {calendar === null ? (
              <Alert tone="danger" title="Die Termine lassen sich gerade nicht laden">
                <p>Bitte versuch es gleich noch einmal. Die Messe-Post kannst du trotzdem bestellen.</p>
              </Alert>
            ) : calendar.upcoming.length > 0 ? (
              <UpcomingFairs fairs={calendar.upcoming} today={today} />
            ) : (
              <div className="rounded-lg border border-dashed border-line-strong p-8 sm:p-10">
                <p className="label-caps text-ink-tertiary">Fahrplan in Arbeit</p>
                <p className="mt-3 max-w-md text-body-lg text-ink-secondary">
                  Die nächsten Messen stehen noch nicht fest. Mit der Messe-Post erfährst du als Erstes davon.
                </p>
              </div>
            )}
          </section>

          {calendar !== null && calendar.past.length > 0 ? (
            <section aria-labelledby="rueckblick" className="mt-16 lg:mt-20">
              <h2 id="rueckblick" className="text-heading">
                Rückblick
              </h2>
              <div className="mt-8">
                <PastFairs fairs={calendar.past} />
              </div>
            </section>
          ) : null}
        </div>

        <aside aria-label="Messe-Post und Kalender" className="space-y-6 lg:sticky lg:top-8">
          <section aria-labelledby="messe-post" className="rounded-lg bg-surface p-6 sm:p-8">
            <p className="label-caps text-ink-tertiary">Messe-Post</p>
            <h2 id="messe-post" className="mt-3 text-heading">
              Keine Messe mehr verpassen
            </h2>
            <p className="mt-3 mb-6 text-small text-ink-secondary">
              Eine kurze E-Mail, sobald wir eine neue Messe ankündigen – sonst nichts.
            </p>
            <FairNewsForm />
          </section>
          <section aria-labelledby="kalender" className="rounded-lg border border-line p-6 sm:p-8">
            <h2 id="kalender" className="text-body font-medium">
              Termine im eigenen Kalender
            </h2>
            <p className="mt-2 mb-5 text-small text-ink-secondary">
              Abonniere unseren Kalender: Neue Messen erscheinen dann von selbst bei dir, ganz ohne E-Mail.
            </p>
            <CalendarSubscription />
          </section>
        </aside>
      </div>
    </div>
  );
}
