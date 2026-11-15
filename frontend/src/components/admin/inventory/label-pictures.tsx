"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { savedName } from "@/lib/api/fetcher";
import { printLabels } from "@/lib/api/generated/admin-inventory/admin-inventory";
import {
  LabelFormat,
  LabelSheet,
  type LabelsIn,
  type VariantLabelsIn,
} from "@/lib/api/generated/model";
import { errorMessage } from "@/lib/i18n/problems";

import type { ModelLabels } from "./label-printer";

/** More labels than this come only as a ZIP, not one by one on the page. */
export const PICTURES_SHOWN_MAX = 24;

type Picture = { url: string; name: string; code: string; copies: number };
type Codes = {
  unitCodes: readonly string[];
  models?: readonly ModelLabels[];
  locationCodes: readonly string[];
  partNumbers: readonly string[];
};

/** All labels of a model look the same: the app prints one picture as often as needed. */
function variantsOf(models: readonly ModelLabels[]): VariantLabelsIn[] {
  return models.map((model) => ({
    variant_id: model.variantId,
    quantity: model.quantity,
  }));
}

/** One request per label: each code alone, in the order the labels are printed; one
 * picture per model, however many of its labels there are. */
function singles({
  unitCodes,
  models = [],
  locationCodes,
  partNumbers,
}: Codes): { code: string; copies: number; body: LabelsIn }[] {
  const body = (
    unit: string[],
    location: string[],
    part: string[],
    variants: VariantLabelsIn[] = [],
  ): LabelsIn => ({
    sheet: LabelSheet.ql_62x29,
    format: LabelFormat.png,
    unit_codes: unit,
    variants,
    location_codes: location,
    part_numbers: part,
  });
  return [
    ...unitCodes.map((code) => ({ code, copies: 1, body: body([code], [], []) })),
    ...models.map((model) => ({
      code: model.sku,
      copies: model.quantity,
      body: body([], [], [], variantsOf([{ ...model, quantity: 1 }])),
    })),
    ...locationCodes.map((code) => ({ code, copies: 1, body: body([], [code], []) })),
    ...partNumbers.map((code) => ({ code, copies: 1, body: body([], [], [code]) })),
  ];
}

function fileName(code: string): string {
  return `etikett-${code.replace(/[^A-Za-z0-9-]/g, "")}.png`;
}

/**
 * The labels of the QL roll as pictures at 300 dpi, black and white: Brother's apps
 * (iPrint&Label on the phone, P-touch Editor on the Mac) print pictures, not PDFs.
 */
export function LabelPictures({
  unitCodes,
  models = [],
  locationCodes,
  partNumbers,
}: Codes) {
  const count =
    unitCodes.length +
    models.reduce((sum, model) => sum + model.quantity, 0) +
    locationCodes.length +
    partNumbers.length;
  const [pictures, setPictures] = useState<Picture[] | null>(null);
  const [zip, setZip] = useState<{ url: string; name: string } | null>(null);
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(
    () => () => {
      pictures?.forEach((picture) => URL.revokeObjectURL(picture.url));
    },
    [pictures],
  );
  useEffect(
    () => () => {
      if (zip) {
        URL.revokeObjectURL(zip.url);
      }
    },
    [zip],
  );

  async function generate() {
    setPending(true);
    setProblem(null);
    try {
      const made: Picture[] = [];
      const one = singles({
        unitCodes,
        models,
        locationCodes,
        partNumbers,
      });
      if (one.length <= PICTURES_SHOWN_MAX) {
        for (const { code, copies, body } of one) {
          const blob = await printLabels(body);
          made.push({
            url: URL.createObjectURL(blob),
            name: savedName(blob) ?? fileName(code),
            code,
            copies,
          });
        }
      }
      setPictures(made);
      if (count > 1) {
        const all = await printLabels({
          sheet: LabelSheet.ql_62x29,
          format: LabelFormat.png,
          unit_codes: [...unitCodes],
          variants: variantsOf(models),
          location_codes: [...locationCodes],
          part_numbers: [...partNumbers],
        });
        setZip({ url: URL.createObjectURL(all), name: savedName(all) ?? "etiketten.zip" });
      }
    } catch (error) {
      setProblem(errorMessage(error));
    } finally {
      setPending(false);
    }
  }

  if (pictures === null) {
    return (
      <div className="space-y-2">
        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={() => void generate()}
          disabled={pending || count === 0}
          aria-busy={pending || undefined}
        >
          {pending
            ? "Bilder werden erstellt …"
            : "Als Bilder für die Brother-App"}
        </Button>
        <p role="alert" className="text-hint font-medium text-danger">
          {problem}
        </p>
      </div>
    );
  }

  return (
    <section aria-label="Etiketten als Bilder" className="space-y-3">
      <p className="text-ink-secondary">
        In der Brother-App „iPrint&amp;Label“ oder im P-touch Editor als Bild
        öffnen und auf der 62-mm-Rolle drucken.
      </p>
      {pictures.length > 0 ? (
        <ul className="grid grid-cols-[repeat(auto-fill,minmax(11rem,1fr))] gap-3">
          {pictures.map((picture) => (
            <li key={picture.url}>
              <figure>
                {/* eslint-disable-next-line @next/next/no-img-element -- a local blob, not an asset */}
                <img
                  src={picture.url}
                  alt={`Etikett ${picture.code}`}
                  className="block w-full rounded-xs border border-line-control bg-white"
                />
                <figcaption className="mt-1 flex items-center justify-between gap-2">
                  <span className="truncate font-mono text-hint text-ink-tertiary">
                    {picture.copies > 1
                      ? `${picture.copies} × ${picture.code}`
                      : picture.code}
                  </span>
                  <a
                    href={picture.url}
                    download={picture.name}
                    className="text-hint text-accent hover:underline"
                  >
                    Speichern
                  </a>
                </figcaption>
              </figure>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-ink-secondary">
          Bei mehr als {PICTURES_SHOWN_MAX} Etiketten gibt es die Bilder nur
          gesammelt als ZIP.
        </p>
      )}
      {zip ? (
        <Button asChild size="sm">
          <a href={zip.url} download={zip.name}>
            Alle Bilder als ZIP
          </a>
        </Button>
      ) : null}
    </section>
  );
}
