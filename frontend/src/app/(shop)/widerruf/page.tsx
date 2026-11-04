import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";

import { LegalSection, LegalStand, LegalSubheading, LegalText } from "@/components/site/legal-text";
import { PageHeading } from "@/components/site/page-heading";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import type { ImprintOut } from "@/lib/api/generated/model";
import { loadImprint, postalAddress, providerName, WITHDRAWAL_FUNCTION_PATH } from "@/lib/site/imprint";

export const metadata: Metadata = {
  title: "Widerrufsbelehrung",
};

/** "adp-Modelle, Inhaber …, Straße, PLZ Ort, Land, Telefon: …, E-Mail: …" as the model asks for it. */
function contact(imprint: ImprintOut): string {
  return [
    providerName(imprint),
    postalAddress(imprint),
    imprint.phone ? `Telefon: ${imprint.phone}` : "",
    imprint.email ? `E-Mail: ${imprint.email}` : "",
  ]
    .filter(Boolean)
    .join(", ");
}

/**
 * The withdrawal notice for goods in the words of the statutory model (Anlage 1 zu Art. 246a
 * § 1 Abs. 2 Satz 2 EGBGB, as of 19 June 2026), with the provider details from MB_IMPRINT_*
 * and the model form (Anlage 2). The model addresses the reader formally; the shop keeps that
 * here so as not to lose its protection. The paragraph on the withdrawal function follows
 * Gestaltungshinweis 3 as published; check it against BGBl. 2026 I Nr. 28 when it changes.
 */
export default async function WithdrawalPage() {
  await connection();
  const imprint = await loadImprint();

  return (
    <div className="mx-auto max-w-6xl px-5 py-12 sm:px-8 lg:py-20">
      <PageHeading caption="Rechtliches" title="Widerrufsrecht">
        <p>
          Du kannst deine Bestellung innerhalb von 14 Tagen widerrufen, ohne Gründe zu nennen. Am schnellsten geht das
          hier online, mit sofortiger Bestätigung per E-Mail.
        </p>
      </PageHeading>
      <Button asChild className="mt-8">
        <Link href={WITHDRAWAL_FUNCTION_PATH}>Vertrag widerrufen</Link>
      </Button>

      {imprint === null ? (
        <Alert tone="danger" title="Die Widerrufsbelehrung lässt sich gerade nicht laden" className="mt-10 max-w-2xl">
          <p>Bitte versuch es gleich noch einmal. Widerrufen kannst du trotzdem jederzeit über den Knopf oben.</p>
        </Alert>
      ) : (
        <LegalText>
          <p className="text-small text-ink-tertiary">
            Die Belehrung folgt dem gesetzlichen Muster; darum siezen wir dich hier ausnahmsweise.
          </p>

          <LegalSection id="widerrufsbelehrung" title="Widerrufsbelehrung">
            <LegalSubheading>Widerrufsrecht</LegalSubheading>
            <p>Sie haben das Recht, binnen vierzehn Tagen ohne Angabe von Gründen diesen Vertrag zu widerrufen.</p>
            <p>
              Die Widerrufsfrist beträgt vierzehn Tage ab dem Tag, an dem Sie oder ein von Ihnen benannter Dritter, der
              nicht der Beförderer ist, die Waren in Besitz genommen haben bzw. hat.
            </p>
            <p>
              Um Ihr Widerrufsrecht auszuüben, müssen Sie uns ({contact(imprint)}) mittels einer eindeutigen Erklärung
              (z. B. ein mit der Post versandter Brief oder E-Mail) über Ihren Entschluss, diesen Vertrag zu
              widerrufen, informieren. Sie können dafür das beigefügte Muster-Widerrufsformular verwenden, das jedoch
              nicht vorgeschrieben ist.
            </p>
            <p>
              Sie können Ihr Widerrufsrecht auch online unter{" "}
              <Link href={WITHDRAWAL_FUNCTION_PATH} className="break-all text-accent underline underline-offset-4">
                {imprint.site_url}
                {WITHDRAWAL_FUNCTION_PATH}
              </Link>{" "}
              („Vertrag widerrufen“) ausüben. Machen Sie von dieser Möglichkeit Gebrauch, so werden wir Ihnen
              unverzüglich auf einem dauerhaften Datenträger (per E-Mail) eine Bestätigung über den Eingang des
              Widerrufs übermitteln, mit seinem Inhalt sowie dem Datum und der Uhrzeit seines Eingangs.
            </p>
            <p>
              Zur Wahrung der Widerrufsfrist reicht es aus, dass Sie die Mitteilung über die Ausübung des
              Widerrufsrechts vor Ablauf der Widerrufsfrist absenden.
            </p>

            <LegalSubheading>Folgen des Widerrufs</LegalSubheading>
            <p>
              Wenn Sie diesen Vertrag widerrufen, haben wir Ihnen alle Zahlungen, die wir von Ihnen erhalten haben,
              einschließlich der Lieferkosten (mit Ausnahme der zusätzlichen Kosten, die sich daraus ergeben, dass Sie
              eine andere Art der Lieferung als die von uns angebotene, günstigste Standardlieferung gewählt haben),
              unverzüglich und spätestens binnen vierzehn Tagen ab dem Tag zurückzuzahlen, an dem die Mitteilung über
              Ihren Widerruf dieses Vertrags bei uns eingegangen ist. Für diese Rückzahlung verwenden wir dasselbe
              Zahlungsmittel, das Sie bei der ursprünglichen Transaktion eingesetzt haben, es sei denn, mit Ihnen wurde
              ausdrücklich etwas anderes vereinbart; in keinem Fall werden Ihnen wegen dieser Rückzahlung Entgelte
              berechnet.
            </p>
            <p>
              Wir können die Rückzahlung verweigern, bis wir die Waren wieder zurückerhalten haben oder bis Sie den
              Nachweis erbracht haben, dass Sie die Waren zurückgesandt haben, je nachdem, welches der frühere Zeitpunkt
              ist.
            </p>
            <p>
              Sie haben die Waren unverzüglich und in jedem Fall spätestens binnen vierzehn Tagen ab dem Tag, an dem
              Sie uns über den Widerruf dieses Vertrags unterrichten, an uns zurückzusenden oder zu übergeben. Die Frist
              ist gewahrt, wenn Sie die Waren vor Ablauf der Frist von vierzehn Tagen absenden.
            </p>
            <p>Sie tragen die unmittelbaren Kosten der Rücksendung der Waren.</p>
            <p>
              Sie müssen für einen etwaigen Wertverlust der Waren nur aufkommen, wenn dieser Wertverlust auf einen zur
              Prüfung der Beschaffenheit, Eigenschaften und Funktionsweise der Waren nicht notwendigen Umgang mit ihnen
              zurückzuführen ist.
            </p>
            <p className="text-small text-ink-tertiary">Ende der Widerrufsbelehrung</p>
          </LegalSection>

          <LegalSection id="ausschluss" title="Ausschluss des Widerrufsrechts">
            <p>
              Das Widerrufsrecht besteht nicht bei Verträgen zur Lieferung von Waren, die nicht vorgefertigt sind und
              für deren Herstellung eine individuelle Auswahl oder Bestimmung durch den Verbraucher maßgeblich ist oder
              die eindeutig auf die persönlichen Bedürfnisse des Verbrauchers zugeschnitten sind (§ 312g Abs. 2 Nr. 1
              BGB). Das betrifft Sonderanfertigungen nach deinen Vorgaben, die wir auf Anfrage vereinbaren. Modelle
              aus dem Katalog, die wir erst nach deiner Bestellung fertigen, kannst du dagegen ganz normal widerrufen.
            </p>
          </LegalSection>

          <LegalSection id="muster-widerrufsformular" title="Muster-Widerrufsformular">
            <p className="text-small">
              (Wenn Sie den Vertrag widerrufen wollen, dann füllen Sie bitte dieses Formular aus und senden Sie es
              zurück.)
            </p>
            <ul className="space-y-3 rounded-md border border-line bg-surface px-6 py-5 text-ink">
              <li>
                – An {providerName(imprint)}, {postalAddress(imprint)}
                {imprint.email ? `, E-Mail: ${imprint.email}` : ""}:
              </li>
              <li>
                – Hiermit widerrufe(n) ich/wir (*) den von mir/uns (*) abgeschlossenen Vertrag über den Kauf der
                folgenden Waren (*)/die Erbringung der folgenden Dienstleistung (*)
              </li>
              <li>– Bestellt am (*)/erhalten am (*)</li>
              <li>– Name des/der Verbraucher(s)</li>
              <li>– Anschrift des/der Verbraucher(s)</li>
              <li>– Unterschrift des/der Verbraucher(s) (nur bei Mitteilung auf Papier)</li>
              <li>– Datum</li>
              <li className="text-small text-ink-tertiary">(*) Unzutreffendes streichen.</li>
            </ul>
          </LegalSection>

          <LegalStand>November 2026</LegalStand>
        </LegalText>
      )}
    </div>
  );
}
