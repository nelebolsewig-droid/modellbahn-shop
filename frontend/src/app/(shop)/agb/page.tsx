import type { Metadata } from "next";
import { connection } from "next/server";

import { LegalSection, LegalStand, LegalText } from "@/components/site/legal-text";
import { PageHeading } from "@/components/site/page-heading";
import { Alert } from "@/components/ui/alert";
import { TextLink } from "@/components/ui/text-link";
import { loadImprint, postalAddress, providerName, WITHDRAWAL_FUNCTION_PATH } from "@/lib/site/imprint";

export const metadata: Metadata = {
  title: "Allgemeine Geschäftsbedingungen",
};

/**
 * The terms of the shop, with the provider details from MB_IMPRINT_*. They describe the
 * checkout as it works (ADR 0009, 0019, 0020): a binding offer with "Zahlungspflichtig
 * bestellen", the contract with the payment, 24 hours to pay. A lawyer should look over
 * them before the first real sale; the shop changes them here, nowhere else.
 */
export default async function TermsPage() {
  await connection();
  const imprint = await loadImprint();

  return (
    <div className="mx-auto max-w-6xl px-5 py-12 sm:px-8 lg:py-20">
      <PageHeading caption="Rechtliches" title="Allgemeine Geschäftsbedingungen">
        <p>Wie ein Kauf in unserem Shop abläuft: vom Warenkorb bis zum Paket.</p>
      </PageHeading>

      {imprint === null ? (
        <Alert tone="danger" title="Die AGB lassen sich gerade nicht laden" className="mt-10 max-w-2xl">
          <p>Bitte versuch es gleich noch einmal.</p>
        </Alert>
      ) : (
        <LegalText>
          <LegalSection id="geltungsbereich" mark="§ 1" title="Geltungsbereich">
            <p>
              (1) Diese Allgemeinen Geschäftsbedingungen gelten für alle Bestellungen über unseren Online-Shop unter{" "}
              <span className="break-all">{imprint.site_url}</span> zwischen dir und uns ({providerName(imprint)}).
            </p>
            <p>
              (2) Verbraucher ist jede natürliche Person, die ein Rechtsgeschäft zu Zwecken abschließt, die
              überwiegend weder ihrer gewerblichen noch ihrer selbständigen beruflichen Tätigkeit zugerechnet werden
              können (§ 13 BGB).
            </p>
            <p>
              (3) Abweichende Bedingungen gelten nur, wenn wir ihnen ausdrücklich zustimmen. Für Käufe über eBay gelten
              die Angaben im jeweiligen eBay-Angebot.
            </p>
          </LegalSection>

          <LegalSection id="vertragspartner" mark="§ 2" title="Vertragspartner">
            <p>
              Dein Vertragspartner ist {providerName(imprint)}, {postalAddress(imprint)}
              {imprint.email ? `, E-Mail: ${imprint.email}` : ""}
              {imprint.phone ? `, Telefon: ${imprint.phone}` : ""}. Weitere Angaben stehen im{" "}
              <TextLink href="/impressum">Impressum</TextLink>.
            </p>
          </LegalSection>

          <LegalSection id="modelle" mark="§ 3" title="Unsere Modelle">
            <p>
              (1) Unsere Modelle entstehen in Handarbeit. Die Fotos zeigen Beispiele; Fertigmodelle sind von Hand
              bemalt, Farbton und kleine Details können deshalb vom Foto etwas abweichen. Bausätze liefern wir
              unbemalt und unmontiert.
            </p>
            <p>
              (2) Unsere Modelle sind Modellbau- und Sammlerartikel für Erwachsene und kein Spielzeug. Sie enthalten
              Kleinteile und sind für Kinder unter 14 Jahren nicht geeignet.
            </p>
          </LegalSection>

          <LegalSection id="vertragsschluss" mark="§ 4" title="Bestellung und Vertragsschluss">
            <p>
              (1) Die Darstellung der Modelle im Shop ist kein bindendes Angebot, sondern eine Einladung zur
              Bestellung.
            </p>
            <p>
              (2) Du legst Modelle in den Warenkorb und gibst an der Kasse deine Lieferadresse an, als Gast mit
              E-Mail-Adresse oder mit deinem Kundenkonto. Vor dem Absenden siehst du alle Artikel, Preise,
              Versandkosten und die Lieferzeit und kannst deine Eingaben korrigieren oder im Warenkorb ändern. Mit
              einem Klick auf „Zahlungspflichtig bestellen“ gibst du ein verbindliches Angebot zum Kauf ab.
            </p>
            <p>
              (3) Den Eingang deiner Bestellung bestätigen wir dir sofort per E-Mail. Diese Eingangsbestätigung ist
              noch keine Annahme deines Angebots.
            </p>
            <p>
              (4) Wir nehmen dein Angebot an, indem wir dir den Eingang deiner Zahlung per E-Mail bestätigen
              („Zahlung eingegangen“). Damit kommt der Kaufvertrag zustande.
            </p>
            <p>
              (5) An dein Angebot bist du 24 Stunden gebunden, bei Vorkasse per Überweisung zehn Tage. Geht deine
              Zahlung in dieser Zeit nicht ein, stornieren wir die Bestellung und sagen dir per E-Mail Bescheid. Geht
              danach doch noch Geld ein, erstatten wir es dir.
            </p>
            <p>
              (6) Wir speichern deine Bestellung mit Artikeln, Preisen und Lieferadresse und schicken sie dir per
              E-Mail. Mit Kundenkonto findest du sie auch unter „Mein Konto“. Diese AGB kannst du hier jederzeit
              aufrufen und ausdrucken. Vertragssprache ist Deutsch.
            </p>
          </LegalSection>

          <LegalSection id="preise" mark="§ 5" title="Preise und Versandkosten">
            <p>(1) Alle Preise sind Endpreise in Euro und enthalten die gesetzliche Mehrwertsteuer.</p>
            <p>
              (2) Dazu kommen je Bestellung Versandkosten. Sie stehen auf der Seite{" "}
              <TextLink href="/versand">Versand und Lieferung</TextLink> und werden dir im Warenkorb und vor dem
              Absenden der Bestellung angezeigt.
            </p>
          </LegalSection>

          <LegalSection id="lieferung" mark="§ 6" title="Lieferung">
            <p>(1) Wir liefern nach Deutschland und in alle anderen Länder der Europäischen Union.</p>
            <p>
              (2) Die Lieferzeit steht am Artikel und vor dem Absenden der Bestellung; sie beginnt mit dem Eingang
              deiner Zahlung. Vorrätige Modelle verschicken wir in der Regel innerhalb von 1 bis 3 Werktagen. Modelle,
              die wir erst nach deiner Bestellung fertigen, haben die am Artikel genannte Lieferzeit.
            </p>
            <p>
              (3) Können wir ein Modell entgegen unserer Angabe nicht liefern, etwa weil ein Material nicht mehr zu
              bekommen ist, sagen wir dir sofort Bescheid und erstatten dir bereits gezahlte Beträge.
            </p>
          </LegalSection>

          <LegalSection id="zahlung" mark="§ 7" title="Zahlung">
            <p>
              (1) Du bezahlst direkt nach der Bestellung über unseren Zahlungsdienst SumUp, mit Kredit- oder Debitkarte,
              je nach Gerät auch mit Apple Pay oder Google Pay. Die Zahlungsdaten gibst du auf der Seite von SumUp ein;
              wir erhalten sie nicht. Bieten wir es auf der Bezahlseite an, kannst du stattdessen per Vorkasse bezahlen:
              Du überweist den Betrag mit der Bestellnummer als Verwendungszweck auf unser Konto, das wir dir auf der
              Bezahlseite und per E-Mail nennen.
            </p>
            <p>
              (2) Der Kaufpreis ist mit der Bestellung fällig. Bezahlen kannst du bis 24 Stunden nach der Bestellung,
              per Vorkasse bis zehn Tage danach. Bei Vorkasse verschicken wir die Ware, sobald das Geld auf unserem Konto
              ist.
            </p>
          </LegalSection>

          <LegalSection id="eigentumsvorbehalt" mark="§ 8" title="Eigentumsvorbehalt">
            <p>Die Ware bleibt bis zur vollständigen Bezahlung unser Eigentum.</p>
          </LegalSection>

          <LegalSection id="widerrufsrecht" mark="§ 9" title="Widerrufsrecht">
            <p>
              Als Verbraucher hast du ein Widerrufsrecht. Wie es funktioniert, steht in der{" "}
              <TextLink href="/widerruf">Widerrufsbelehrung</TextLink>; widerrufen kannst du auch direkt online unter{" "}
              <TextLink href={WITHDRAWAL_FUNCTION_PATH}>Vertrag widerrufen</TextLink>. Die unmittelbaren Kosten der
              Rücksendung trägst du. Kein Widerrufsrecht besteht bei Sonderanfertigungen nach deinen Vorgaben.
            </p>
          </LegalSection>

          <LegalSection id="maengel" mark="§ 10" title="Mängelhaftung">
            <p>
              Es gilt die gesetzliche Mängelhaftung. Ist ein Modell mangelhaft, kannst du Nacherfüllung verlangen, also
              Reparatur oder Ersatz; unter den gesetzlichen Voraussetzungen auch den Preis mindern, vom Vertrag
              zurücktreten oder Schadensersatz verlangen. Ansprüche wegen Mängeln verjähren bei neuer Ware zwei Jahre
              nach der Lieferung. Schreib uns bei einem Mangel am besten gleich mit ein paar Fotos.
            </p>
          </LegalSection>

          <LegalSection id="haftung" mark="§ 11" title="Haftung">
            <p>
              (1) Wir haften unbeschränkt bei Vorsatz und grober Fahrlässigkeit, für Schäden an Leben, Körper oder
              Gesundheit, nach dem Produkthaftungsgesetz und soweit wir eine Garantie übernommen haben.
            </p>
            <p>
              (2) Bei leichter Fahrlässigkeit haften wir nur, wenn wir eine wesentliche Vertragspflicht verletzen,
              also eine Pflicht, deren Erfüllung den Vertrag erst möglich macht und auf die du vertrauen darfst. Die
              Haftung ist dann auf den vorhersehbaren, vertragstypischen Schaden begrenzt.
            </p>
            <p>(3) Diese Grenzen gelten auch für unsere Mitarbeiter und Beauftragten.</p>
          </LegalSection>

          <LegalSection id="streitbeilegung" mark="§ 12" title="Streitbeilegung">
            <p>
              Wir sind nicht bereit und nicht verpflichtet, an Streitbeilegungsverfahren vor einer
              Verbraucherschlichtungsstelle teilzunehmen. Schreib uns bei Fragen oder Problemen einfach; wir finden
              eine Lösung.
            </p>
          </LegalSection>

          <LegalSection id="schluss" mark="§ 13" title="Schlussbestimmungen">
            <p>
              Es gilt deutsches Recht unter Ausschluss des UN-Kaufrechts. Bist du Verbraucher, gilt das nur, soweit dir
              dadurch nicht der Schutz zwingender Bestimmungen des Staates entzogen wird, in dem du deinen gewöhnlichen
              Aufenthalt hast.
            </p>
          </LegalSection>

          <LegalStand>November 2026</LegalStand>
        </LegalText>
      )}
    </div>
  );
}
