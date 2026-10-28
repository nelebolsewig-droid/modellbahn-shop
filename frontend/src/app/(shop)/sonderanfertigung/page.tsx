import type { Metadata } from "next";
import { connection } from "next/server";
import type { ReactNode } from "react";

import { PageHeading } from "@/components/site/page-heading";
import { DRAWING } from "@/components/ui/blueprint-drawing";
import { Button } from "@/components/ui/button";
import { loadImprint, phoneHref } from "@/lib/site/imprint";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
  title: "Sonderanfertigung",
  description: "Einzelstücke und Kleinserien im 3D-Druck und Lasercutting, nach deinen Vorstellungen.",
};

const STROKE = { strokeWidth: 1, vectorEffect: "non-scaling-stroke" } as const;

const GRID =
  "bg-stage bg-[image:linear-gradient(var(--drawing-grid)_1px,transparent_1px),linear-gradient(90deg,var(--drawing-grid)_1px,transparent_1px)] bg-[size:16px_16px] bg-[position:-1px_-1px]";

/** A print head laying the last layers of a part. */
function PrintDrawing() {
  return (
    <svg viewBox="0 0 160 96" aria-hidden="true" className="block h-auto w-full">
      <path className={DRAWING.line} d="M20 82 H140" {...STROKE} />
      <path className={DRAWING.face} d="M44 82 V58 H116 V82 Z" {...STROKE} />
      <path className={DRAWING.helper} d="M44 76 H116 M44 70 H116 M44 64 H116" {...STROKE} />
      <path className={DRAWING.line} d="M58 58 V52 H92" {...STROKE} />
      <path className={DRAWING.face} d="M86 22 H110 V36 H86 Z" {...STROKE} />
      <path className={DRAWING.face} d="M93 36 H103 L98 46 Z" {...STROKE} />
      <path className={DRAWING.helper} d="M98 46 V52" {...STROKE} />
      <path
        className={DRAWING.dimension}
        d="M118 58 H136 M118 64 H136 M131 46 V76 M127 62 L135 54 M127 68 L135 60"
        {...STROKE}
      />
      <text className={DRAWING.figure} x="138" y="54">
        0,1
      </text>
    </svg>
  );
}

/** A laser head cutting a contour out of a plate. */
function LaserDrawing() {
  return (
    <svg viewBox="0 0 160 96" aria-hidden="true" className="block h-auto w-full">
      <path className={DRAWING.face} d="M16 64 L52 52 H148 L112 64 Z" {...STROKE} />
      <path className={DRAWING.line} d="M16 64 V70 H112 V64 M112 70 L148 58 V52" {...STROKE} />
      <path className={DRAWING.helper} d="M50 59 Q66 54 80 57 T106 56" {...STROKE} />
      <path className={DRAWING.line} d="M66 56.5 Q72 55.2 80 57" {...STROKE} />
      <path className={DRAWING.face} d="M70 14 H90 V28 H70 Z" {...STROKE} />
      <path className={DRAWING.face} d="M75 28 H85 L80 36 Z" {...STROKE} />
      <path className={DRAWING.dimension} d="M80 36 V56" {...STROKE} />
      <circle className="fill-drawing-dimension" cx="80" cy="57" r="1.5" />
    </svg>
  );
}

type TechniqueProps = { title: string; drawing: ReactNode; items: readonly [string, string][] };

function Technique({ title, drawing, items }: TechniqueProps) {
  return (
    <section aria-labelledby={`verfahren-${title}`} className="overflow-hidden rounded-lg bg-surface">
      <div className={cn(GRID, "px-8 pt-8 pb-6")}>
        <div className="mx-auto max-w-xs">{drawing}</div>
      </div>
      <div className="p-6 sm:p-8">
        <h2 id={`verfahren-${title}`} className="text-heading">
          {title}
        </h2>
        <ul className="mt-5 space-y-4">
          {items.map(([head, text]) => (
            <li key={head} className="border-t border-line pt-4">
              <p className="font-medium">{head}</p>
              <p className="mt-1 text-small text-ink-secondary">{text}</p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

const STEPS = [
  { title: "Schreib uns", text: "Maßstab, Fotos oder Zeichnung vom Vorbild und die Stückzahl – je mehr wir wissen, desto besser." },
  { title: "Dein Angebot", text: "Wir sagen dir, was sich umsetzen lässt, in welchem Material und was es kostet." },
  { title: "Fertigung", text: "Wir drucken, schneiden und prüfen dein Teil und schicken es dir zu." },
] as const;

export default async function CustomWorkPage() {
  await connection();
  const imprint = await loadImprint();
  const mail = imprint?.email ? `mailto:${imprint.email}?subject=${encodeURIComponent("Sonderanfertigung")}` : null;

  return (
    <div className="mx-auto max-w-6xl px-5 py-12 sm:px-8 lg:py-20">
      <PageHeading caption="Service" title="Sonderanfertigung">
        <p>
          Ein Modell, das es nirgends gibt? Ein Bauteil, das fehlt? Mit 3D-Druck und Lasercutting fertigen wir
          präzise Einzelstücke und Kleinserien – ganz nach deinen Vorstellungen.
        </p>
      </PageHeading>

      <div className="mt-12 grid gap-6 lg:mt-16 lg:grid-cols-2">
        <Technique
          title="3D-Druck"
          drawing={<PrintDrawing />}
          items={[
            ["Prototypen und Einzelstücke", "Vom ersten Muster bis zum maßgeschneiderten Teil für deine Anlage."],
            ["Kleinserien", "Hochwertige, detailgenaue Teile in geringer Stückzahl."],
            ["Materialvielfalt", "Von Kunststoffen über Metalle bis zu Spezialmaterialien."],
          ]}
        />
        <Technique
          title="Lasercutting"
          drawing={<LaserDrawing />}
          items={[
            ["Präzisionsschnitt", "Holz, Acryl und weitere Materialien, sauber auf den Zehntelmillimeter."],
            ["Gravuren", "Schilder, Geschenke und Dekorationen mit deinem Motiv."],
            ["Materialkombinationen", "Verschiedene Werkstoffe in einem Werkstück."],
          ]}
        />
      </div>

      <section aria-labelledby="ablauf" className="mt-16 lg:mt-24">
        <h2 id="ablauf" className="text-heading">
          So kommst du zu deinem Teil
        </h2>
        <ol className="mt-8 grid gap-8 sm:grid-cols-3">
          {STEPS.map((step, index) => (
            <li key={step.title} className="border-t border-line-strong pt-5">
              <p className="font-mono text-hint text-ink-tertiary">0{index + 1}</p>
              <p className="mt-2 text-[1.25rem] leading-7 tracking-[-0.01em]">{step.title}</p>
              <p className="mt-2 text-ink-secondary">{step.text}</p>
            </li>
          ))}
        </ol>
      </section>

      {imprint?.email ? (
        <section
          aria-labelledby="anfrage"
          className="mt-16 flex flex-col gap-6 rounded-lg bg-selected p-8 text-on-selected sm:flex-row sm:items-center sm:justify-between sm:p-10 lg:mt-24"
        >
          <div>
            <h2 id="anfrage" className="text-heading">
              Erzähl uns von deinem Projekt
            </h2>
            <p className="mt-2 text-on-selected/80">Wir machen dir gern ein unverbindliches Angebot.</p>
          </div>
          <div className="flex flex-wrap gap-3">
            {mail ? (
              <Button asChild className="bg-canvas text-ink hover:bg-stage">
                <a href={mail}>E-Mail schreiben</a>
              </Button>
            ) : null}
            {imprint.phone ? (
              <Button asChild variant="secondary" className="border-on-selected/50 text-on-selected hover:border-on-selected">
                <a href={phoneHref(imprint.phone)}>{imprint.phone}</a>
              </Button>
            ) : null}
          </div>
        </section>
      ) : null}
    </div>
  );
}
