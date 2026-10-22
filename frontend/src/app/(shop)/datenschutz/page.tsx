import type { Metadata } from "next";

import { PageHeading } from "@/components/site/page-heading";

export const metadata: Metadata = {
  title: "Datenschutz",
};

export default function PrivacyPage() {
  return (
    <div className="mx-auto max-w-6xl px-5 py-12 sm:px-8 lg:py-20">
      <PageHeading caption="Rechtliches" title="Datenschutz">
        <p>
          Die vollständige Datenschutzerklärung folgt vor dem Verkaufsstart. Was heute schon gilt:
        </p>
      </PageHeading>
      <ul className="mt-8 max-w-2xl list-disc space-y-3 pl-5 leading-7">
        <li>
          Für ein Kundenkonto speichern wir deinen Namen, deine E-Mail-Adresse und dein Passwort –
          das Passwort nur als nicht umkehrbaren Hash.
        </li>
        <li>
          Solange du angemeldet bist, setzen wir ein technisch notwendiges Sitzungscookie. Zu jeder
          Sitzung merken wir uns, wann sie begonnen hat und zuletzt benutzt wurde, und mit welchem
          Browser.
        </li>
        <li>
          Wie jeder Webserver protokolliert unser Server die Anfragen, die ihn erreichen, mit
          IP-Adresse und Zeitpunkt, um Fehler und Missbrauch zu erkennen.
        </li>
        <li>
          Du kannst dein Konto jederzeit unter „Mein Konto“ selbst löschen. Wir entfernen dann
          Namen, E-Mail-Adresse und Passwort und beenden alle Sitzungen.
        </li>
      </ul>
    </div>
  );
}
