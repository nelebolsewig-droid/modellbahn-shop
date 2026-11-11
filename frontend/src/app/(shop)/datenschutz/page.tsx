import type { Metadata } from "next";
import { connection } from "next/server";

import { LegalSection, LegalStand, LegalSubheading, LegalText } from "@/components/site/legal-text";
import { PageHeading } from "@/components/site/page-heading";
import { Alert } from "@/components/ui/alert";
import { TextLink } from "@/components/ui/text-link";
import { loadImprint, postalAddress, providerName } from "@/lib/site/imprint";

export const metadata: Metadata = {
  title: "Datenschutz",
};

/**
 * The privacy notice (Art. 13 DSGVO), with the controller from MB_IMPRINT_*. Every period it
 * names is the shop's own: carts 30 days (CART_LIFETIME), customer sessions 30 days, staff
 * sessions 12 hours, rate limits 10 minutes, backups 14 days on the server and at Hetzner
 * (scripts/sicherung.sh, ADR 0025), logs at most 50 MB per service (docker-compose.yml).
 * Change it here when any of them changes.
 */
export default async function PrivacyPage() {
  await connection();
  const imprint = await loadImprint();

  return (
    <div className="mx-auto max-w-6xl px-5 py-12 sm:px-8 lg:py-20">
      <PageHeading caption="Rechtliches" title="Datenschutz">
        <p>
          Wir verarbeiten nur, was wir für deine Bestellung und den Shop brauchen. Wir setzen keine Analyse- oder
          Werbe-Tracker ein und binden keine Inhalte anderer Anbieter ein; auch die Schriften liefern wir selbst aus.
        </p>
      </PageHeading>

      {imprint === null ? (
        <Alert tone="danger" title="Die Datenschutzerklärung lässt sich gerade nicht laden" className="mt-10 max-w-2xl">
          <p>Bitte versuch es gleich noch einmal.</p>
        </Alert>
      ) : (
        <LegalText>
          <LegalSection id="verantwortlich" mark="1" title="Wer verantwortlich ist">
            <p>
              Verantwortlich im Sinne der Datenschutz-Grundverordnung (DSGVO) ist {providerName(imprint)},{" "}
              {postalAddress(imprint)}
              {imprint.email ? `, E-Mail: ${imprint.email}` : ""}
              {imprint.phone ? `, Telefon: ${imprint.phone}` : ""}. Bei Fragen zum Datenschutz schreib uns einfach.
            </p>
          </LegalSection>

          <LegalSection id="server" mark="2" title="Server, Protokolle und Sicherungen">
            <p>
              Der Shop läuft auf unserem eigenen Server bei Strato in Deutschland; dort liegen alle Daten,
              verschlüsselte Kopien der Sicherungen zusätzlich bei Hetzner (siehe unten). Mit Strato haben wir einen
              Vertrag zur Auftragsverarbeitung (Art. 28 DSGVO).
            </p>
            <p>
              Wie jeder Webserver protokolliert unser Server die Anfragen, die ihn erreichen: IP-Adresse, Zeitpunkt,
              aufgerufene Adresse und Browser. Wir brauchen das, um Fehler und Angriffe zu erkennen (berechtigtes
              Interesse, Art. 6 Abs. 1 lit. f DSGVO). Die Protokolle haben eine feste Größe von höchstens 50 MB je
              Dienst; ist sie erreicht, werden die ältesten Einträge automatisch gelöscht.
            </p>
            <p>
              Zum Schutz vor Missbrauch zählen wir außerdem, wie oft sich jemand von einer IP-Adresse aus anmeldet,
              bestellt oder die Messe-Post bestellt. Die Zählung liegt nur im Arbeitsspeicher und verfällt nach zehn
              Minuten.
            </p>
            <p>
              Die Datenbank sichern wir jede Nacht. Eine Kopie jeder Sicherung legen wir zusätzlich verschlüsselt bei
              einem Speicheranbieter in Deutschland ab, der Hetzner Online GmbH in Gunzenhausen; den Schlüssel haben
              nur wir. Auch mit Hetzner haben wir einen Vertrag zur Auftragsverarbeitung (Art. 28 DSGVO). Die
              Sicherungen bewahren wir an beiden Orten 14 Tage auf; was du löschen lässt, verschwindet spätestens dann
              auch aus ihnen.
            </p>
          </LegalSection>

          <LegalSection id="cookies" mark="3" title="Cookies">
            <p>Wir setzen nur Cookies, ohne die der Shop nicht funktioniert (§ 25 Abs. 2 Nr. 2 TDDDG):</p>
            <ul className="list-disc space-y-2 pl-5">
              <li>
                <code className="font-mono text-small">mb_cart</code> merkt sich deinen Warenkorb, 30 Tage lang.
              </li>
              <li>
                <code className="font-mono text-small">mb_session</code> hält dich angemeldet, solange du dich nicht
                abmeldest, höchstens 30 Tage.
              </li>
              <li>
                <code className="font-mono text-small">mb_admin</code> gilt nur für unsere Mitarbeiter im Stellwerk,
                höchstens 12 Stunden.
              </li>
            </ul>
          </LegalSection>

          <LegalSection id="konto" mark="4" title="Kundenkonto">
            <p>
              Für ein Kundenkonto speichern wir deinen Namen, deine E-Mail-Adresse und dein Passwort, das Passwort nur
              als nicht umkehrbaren Hash. Zu jeder Sitzung merken wir uns, wann sie begonnen hat, wann sie zuletzt
              benutzt wurde und mit welchem Browser. Dein Adressbuch speichern wir, damit du Adressen nicht neu eingeben
              musst. Rechtsgrundlage ist der Vertrag über dein Konto (Art. 6 Abs. 1 lit. b DSGVO).
            </p>
            <p>
              Du kannst dein Konto jederzeit unter „Mein Konto“ selbst löschen. Wir entfernen dann Namen, E-Mail-Adresse,
              Passwort und Adressbuch und beenden alle Sitzungen. Bestellungen bleiben, solange wir sie aufbewahren
              müssen (Abschnitt 5).
            </p>
          </LegalSection>

          <LegalSection id="bestellungen" mark="5" title="Bestellungen">
            <p>
              Für eine Bestellung verarbeiten wir deinen Namen, deine Lieferadresse, deine E-Mail-Adresse, die Artikel
              und den Stand der Zahlung, um den Vertrag zu erfüllen (Art. 6 Abs. 1 lit. b DSGVO). Bestellst du als Gast
              und bestätigst später ein Konto mit derselben E-Mail-Adresse, erscheint die Bestellung in diesem Konto.
            </p>
            <p>
              Bestellungen bewahren wir so lange auf, wie Handels- und Steuerrecht es verlangen (§ 257 HGB, § 147 AO;
              Art. 6 Abs. 1 lit. c DSGVO), und löschen sie danach.
            </p>
            <LegalSubheading>E-Mails zur Bestellung</LegalSubheading>
            <p>
              Eingang, Zahlung, Versand und Stornierung bestätigen wir dir per E-Mail. Die E-Mails verschickt unser
              Postfach bei Strato.
            </p>
            <LegalSubheading>Zahlung mit SumUp</LegalSubheading>
            <p>
              Bezahlst du eine Bestellung, gibst du deine Zahlungsdaten auf der Seite von SumUp ein, unserem
              Zahlungsdienst. Wir übermitteln SumUp dafür Bestellnummer und Betrag und erfahren nur, ob die Zahlung
              eingegangen ist; deine Kartendaten sehen wir nicht. Was SumUp mit deinen Daten tut, steht in den
              Datenschutzhinweisen von SumUp (Art. 6 Abs. 1 lit. b DSGVO).
            </p>
            <LegalSubheading>Zahlung per Überweisung</LegalSubheading>
            <p>
              Bezahlst du per Vorkasse, sehen wir im Kontoauszug, was deine Bank mit der Überweisung übermittelt: deinen
              Namen, deine IBAN, Betrag und Verwendungszweck. Damit ordnen wir die Zahlung deiner Bestellung zu und
              überweisen, falls nötig, Geld auf dieses Konto zurück (Art. 6 Abs. 1 lit. b DSGVO). Aufbewahrt wird der
              Kontoauszug so lange, wie Handels- und Steuerrecht es verlangen (Art. 6 Abs. 1 lit. c DSGVO).
            </p>
            <LegalSubheading>Versand</LegalSubheading>
            <p>
              Für den Versand geben wir deinen Namen und deine Lieferadresse an das Versandunternehmen weiter, das dein
              Paket zustellt (Art. 6 Abs. 1 lit. b DSGVO). Deine E-Mail-Adresse und Telefonnummer geben wir dafür nicht
              weiter.
            </p>
            <LegalSubheading>Widerruf</LegalSubheading>
            <p>
              Widerrufst du einen Vertrag über „Vertrag widerrufen“, speichern wir deinen Namen, die Bestellnummer, deine
              E-Mail-Adresse, was du widerrufst und wann der Widerruf eingegangen ist, und schicken dir die
              Eingangsbestätigung. Dazu sind wir verpflichtet (Art. 6 Abs. 1 lit. c DSGVO); aufbewahrt wird der
              Widerruf wie die Bestellung.
            </p>
          </LegalSection>

          <LegalSection id="ebay" mark="6" title="Käufe über eBay">
            <p>
              Kaufst du eines unserer Modelle über eBay, gibt eBay uns deinen eBay-Benutzernamen, Namen, Lieferadresse
              und die gekaufte Ware weiter, damit wir liefern können (Art. 6 Abs. 1 lit. b DSGVO). Für deine Daten bei
              eBay gilt die Datenschutzerklärung von eBay. Meldet eBay, dass du dein Konto geschlossen hast, löschen wir
              Benutzernamen, E-Mail-Adresse und Anschrift aus unseren Angaben zu deinen eBay-Käufen, soweit wir sie nicht
              für die Aufbewahrungsfristen behalten müssen.
            </p>
          </LegalSection>

          <LegalSection id="messe-post" mark="7" title="Messe-Post">
            <p>
              Für die Messe-Post speichern wir deine E-Mail-Adresse, wann du sie bestellt hast und welchen
              Einwilligungstext du gesehen hast. Ankündigungen bekommst du erst, wenn du den Link in unserer
              Bestätigungsmail anklickst (Double-Opt-in); unbestätigte Anmeldungen löschen wir nach sieben Tagen.
              Rechtsgrundlage ist deine Einwilligung (Art. 6 Abs. 1 lit. a DSGVO). Du kannst sie jederzeit mit dem Link
              in jeder Mail widerrufen; wir löschen deine Adresse dann sofort.
            </p>
          </LegalSection>

          <LegalSection id="anfragen" mark="8" title="Anfragen">
            <p>
              Schreibst du uns oder rufst uns an, etwa wegen einer Sonderanfertigung, verarbeiten wir deine Angaben, um
              deine Anfrage zu beantworten (Art. 6 Abs. 1 lit. b und f DSGVO), und löschen sie, wenn sie erledigt ist
              und keine Aufbewahrungspflicht besteht.
            </p>
          </LegalSection>

          <LegalSection id="links" mark="9" title="Links zu anderen Seiten">
            <p>
              Die Links „Route planen“ (OpenStreetMap) und zu den Websites der Messen öffnen diese Seiten erst auf deinen
              Klick; vorher geht nichts an sie.
            </p>
          </LegalSection>

          <LegalSection id="rechte" mark="10" title="Deine Rechte">
            <p>
              Du hast das Recht auf Auskunft über deine Daten (Art. 15 DSGVO), auf Berichtigung (Art. 16), Löschung (Art.
              17), Einschränkung der Verarbeitung (Art. 18) und Datenübertragbarkeit (Art. 20). Einer Verarbeitung aus
              berechtigtem Interesse kannst du widersprechen (Art. 21), eine Einwilligung jederzeit für die Zukunft
              widerrufen. Schreib uns dafür einfach an die Adresse oben.
            </p>
            <p>
              Du kannst dich außerdem bei einer Datenschutz-Aufsichtsbehörde beschweren (Art. 77 DSGVO), etwa bei der
              Behörde des Landes, in dem du wohnst, oder der für unseren Sitz.
            </p>
            <p>
              Abgesehen von Käufen über eBay, für die eBays eigene Regeln gelten, übermitteln wir keine Daten in Länder
              außerhalb der EU. Automatisierte Entscheidungen über dich treffen wir nicht. Weitere Angaben zu uns stehen
              im <TextLink href="/impressum">Impressum</TextLink>.
            </p>
          </LegalSection>

          <LegalStand>November 2026</LegalStand>
        </LegalText>
      )}
    </div>
  );
}
