"use client";

import { useState } from "react";

import { cn } from "@/lib/utils";

import { ResponsivePicture, type PictureImage } from "./responsive-picture";

export type StageItem = { key: string; image: PictureImage; alt: string };

const ASPECTS = {
  "4/5": "aspect-[4/5]",
  "1/1": "aspect-square",
  "16/10": "aspect-[16/10]",
} as const;

type ProductStageProps = {
  items: readonly StageItem[];
  /** The stage's format (§11.3: 4:5, 1:1 or 16:10); the photo is never cropped. */
  aspect?: keyof typeof ASPECTS;
  /** Layout width of the stage, for the browser's choice of size. */
  sizes?: string;
  className?: string;
};

/**
 * The frameless photo stage of a product page: the photo on the light stage with a
 * lot of room around it, so the details of the print show. Thumbnails below switch
 * the photo, which cross-fades in 320 ms.
 */
export function ProductStage({
  items,
  aspect = "4/5",
  sizes = "(min-width: 1024px) 50vw, 100vw",
  className,
}: ProductStageProps) {
  const [index, setIndex] = useState(0);
  const current = items[Math.min(index, items.length - 1)];

  return (
    <div className={className}>
      <div className={cn("relative rounded-lg bg-stage", ASPECTS[aspect])}>
        {current ? (
          <div key={current.key} className="absolute inset-6 animate-stage-in sm:inset-12">
            <ResponsivePicture image={current.image} alt={current.alt} sizes={sizes} priority />
          </div>
        ) : (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-center">
            <p className="label-caps text-ink-tertiary">Foto folgt</p>
            <p className="max-w-56 text-small text-ink-tertiary">
              Das Modell wird gerade fotografiert.
            </p>
          </div>
        )}
      </div>
      {items.length > 1 ? (
        <ul aria-label="Fotos" className="mt-4 flex flex-wrap gap-3">
          {items.map((item, position) => (
            <li key={item.key}>
              <button
                type="button"
                aria-label={`Foto ${position + 1} von ${items.length}: ${item.alt}`}
                aria-pressed={position === index}
                onClick={() => setIndex(position)}
                className={cn(
                  "block size-18 cursor-pointer overflow-hidden rounded-sm bg-stage p-1.5",
                  "border transition-[border-color] duration-150",
                  position === index ? "border-selected" : "border-transparent hover:border-line-strong",
                )}
              >
                <ResponsivePicture image={item.image} alt="" sizes="72px" variant="thumb" />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
