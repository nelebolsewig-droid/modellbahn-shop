import type { Metadata } from "next";
import { connection } from "next/server";
import type { ReactNode } from "react";

import { PageHeading } from "@/components/site/page-heading";
import { Alert } from "@/components/ui/alert";
import type { ImprintOut } from "@/lib/api/generated/model";
import { loadImprint, phoneHref, providerName } from "@/lib/site/imprint";

export const metadata: Metadata = {
  title: "Impressum",
};

type Cell = { label: string; value: ReactNode; wide?: boolean };

function cells(imprint: ImprintOut): Cell[] {
  const town = [imprint.postal_code, imprint.city].filter(Boolean).join(" ");
  const all: Cell[] = [
    { label: "Anbieter", value: imprint.company || imprint.owner, wide: true },
    ...(imprint.company && imprint.owner && imprint.company !== imprint.owner
      ? [{ label: "Inhaber", value: imprint.owner, wide: true }]
      : []),
    { label: "Anschrift", value: [imprint.street, town].filter(Boolean).join(", "), wide: true },
    { label: "Land", value: imprint.country },
    ...(imprint.phone
      ? [{ label: "Telefon", value: <a href={phoneHref(imprint.phone)} className="hover:underline">{imprint.phone}</a> }]
      : []),
    {
      label: "E-Mail",
      value: (
        <a href={`mailto:${imprint.email}`} className="break-all hover:underline">
          {imprint.email}
        </a>
      ),
    },
    ...(imprint.vat_id ? [{ label: "USt-IdNr.", value: imprint.vat_id }] : []),
  ];
  // Half cells go in pairs; a single one left over takes the whole row.
  const half = all.filter((cell) => !cell.wide);
  const last = half.at(-1);
  if (half.length % 2 === 1 && last !== undefined) {
    last.wide = true;
  }
  return all;
}

/**
 * The provider details (§ 5 DDG), from the backend's MB_IMPRINT_* settings, laid out
 * like the title block of a technical drawing. Without a USt-IdNr. that row is left
 * out; the EU's ODR platform closed in July 2025, so there is no link to it.
 */
export default async function ImprintPage() {
  // The details come from the server's configuration; read them per request.
  await connection();
  const imprint = await loadImprint();

  return (
    <div className="mx-auto max-w-6xl px-5 py-12 sm:px-8 lg:py-20">
      <PageHeading caption="Rechtliches" title="Impressum" />

      {imprint === null ? (
        <Alert tone="danger" title="Das Impressum lässt sich gerade nicht laden" className="mt-10 max-w-2xl">
          <p>Bitte versuch es gleich noch einmal.</p>
        </Alert>
      ) : (
        <div className="mt-10 max-w-3xl">
          {imprint.complete ? null : (
            <Alert tone="info" title="Noch nicht vollständig" className="mb-8">
              <p>Die Anbieterangaben sind auf diesem Server noch nicht hinterlegt (MB_IMPRINT_*).</p>
            </Alert>
          )}

          <section aria-labelledby="anbieter">
            <h2 id="anbieter" className="label-caps text-ink-tertiary">
              Angaben gemäß § 5 DDG
            </h2>
            <dl className="mt-4 grid grid-cols-2 gap-px overflow-hidden rounded-xs border border-drawing-line bg-drawing-line">
              {cells(imprint).map((cell) => (
                <div key={cell.label} className={cell.wide ? "col-span-2 bg-stage px-4 py-3" : "bg-stage px-4 py-3"}>
                  <dt className="font-mono text-[0.625rem] leading-[0.875rem] tracking-[0.06em] text-ink-tertiary uppercase">
                    {cell.label}
                  </dt>
                  <dd className="mt-1 text-body-lg">{cell.value}</dd>
                </div>
              ))}
            </dl>
          </section>

          <div className="mt-12 grid gap-10 text-ink-secondary sm:grid-cols-2">
            <section aria-labelledby="verantwortlich">
              <h2 id="verantwortlich" className="text-body font-medium text-ink">
                Verantwortlich für den Inhalt
              </h2>
              <p className="mt-2 text-small">
                Nach § 18 Abs. 2 MStV: {imprint.owner || providerName(imprint)}, Anschrift wie oben.
              </p>
            </section>
            {imprint.vat_id ? (
              <section aria-labelledby="umsatzsteuer">
                <h2 id="umsatzsteuer" className="text-body font-medium text-ink">
                  Umsatzsteuer
                </h2>
                <p className="mt-2 text-small">
                  Umsatzsteuer-Identifikationsnummer nach § 27a Umsatzsteuergesetz: {imprint.vat_id}
                </p>
              </section>
            ) : null}
            <section aria-labelledby="streitbeilegung" className="sm:col-span-2">
              <h2 id="streitbeilegung" className="text-body font-medium text-ink">
                Verbraucherstreitbeilegung
              </h2>
              <p className="mt-2 max-w-2xl text-small">
                Wir sind nicht bereit und nicht verpflichtet, an Streitbeilegungsverfahren vor einer
                Verbraucherschlichtungsstelle teilzunehmen. Schreib uns bei Fragen oder Problemen einfach – wir
                finden eine Lösung.
              </p>
            </section>
          </div>
        </div>
      )}
    </div>
  );
}
