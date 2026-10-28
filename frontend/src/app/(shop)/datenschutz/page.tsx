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
        <li>
          Für die Messe-Post speichern wir deine E-Mail-Adresse, wann du sie bestellt hast und welchen
          Einwilligungstext du gesehen hast. Ankündigungen bekommst du erst, wenn du den Link in unserer
          Bestätigungsmail anklickst (Double-Opt-in); unbestätigte Anmeldungen löschen wir nach sieben
          Tagen. Rechtsgrundlage ist deine Einwilligung (Art. 6 Abs. 1 lit. a DSGVO). Du kannst sie
          jederzeit mit dem Link in jeder Mail widerrufen – wir löschen deine Adresse dann sofort.
        </li>
        <li>
          Die Links „Route planen“ (OpenStreetMap) und zu den Websites der Messen öffnen diese Seiten erst
          auf deinen Klick; vorher geht nichts an sie.
        </li>
      </ul>
    </div>
  );
}
