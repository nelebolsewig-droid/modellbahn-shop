import Link from "next/link";
import type { Route } from "next";

import { labelName } from "@/lib/catalog/filters";
import { formatPrice } from "@/lib/catalog/format";

import { PhotoMark } from "./photo-mark";
import { ResponsivePicture, type PictureImage } from "./responsive-picture";
import { SpecLine } from "./spec-line";

type ProductCardProps = {
  href: Route;
  name: string;
  summary: string;
  /** Scales for sale, by name, e.g. ["H0", "1:24"]. */
  scales: readonly string[];
  priceFromCents: number | null;
  /** Several prices behind it (kit and finished model, other scales): "ab" before the price. */
  priceVaries?: boolean;
  image: PictureImage | null;
  /** What the model is sold as, by name ("Bausatz", "Fertigmodell"), shown on the photo. */
  finishes?: readonly string[];
  /** The label it is sold under; a partner label (not adp) is shown on the photo. */
  label?: string;
  /** The first cards of a page are above the fold. */
  priority?: boolean;
};

/** A model in the catalogue. The whole card is the link; there is no button on it. */
export function ProductCard({
  href,
  name,
  summary,
  scales,
  priceFromCents,
  priceVaries = true,
  image,
  finishes = [],
  label,
  priority = false,
}: ProductCardProps) {
  const partner = label && label !== "adp" ? labelName(label) : null;
  return (
    <Link href={href} className="group block rounded-md">
      <div className="relative aspect-square rounded-md bg-stage transition-colors duration-150 group-hover:bg-sunken">
        {image ? (
          <>
            <div className="absolute inset-6">
              <ResponsivePicture
                image={image}
                alt=""
                sizes="(min-width: 1024px) 30vw, (min-width: 640px) 45vw, 90vw"
                priority={priority}
              />
            </div>
            <PhotoMark finishes={finishes} partner={partner} size="small" />
          </>
        ) : (
          <p className="absolute inset-0 flex items-center justify-center label-caps text-ink-tertiary">
            Foto folgt
          </p>
        )}
      </div>
      {/* The name has the whole width; scales and price share the line below. */}
      <h3 className="mt-4 text-[1.25rem] leading-7 font-bold tracking-[-0.01em] text-ink hyphens-auto break-words group-hover:underline group-hover:underline-offset-4">
        {name}
      </h3>
      <div className="mt-1 flex items-baseline justify-between gap-4">
        {scales.length > 0 ? <SpecLine values={scales} size="small" /> : <span />}
        {priceFromCents !== null ? (
          <p className="shrink-0 text-small text-ink-secondary tabular-nums">
            {priceVaries ? `ab ${formatPrice(priceFromCents)}` : formatPrice(priceFromCents)}
          </p>
        ) : null}
      </div>
      {summary ? <p className="mt-2 line-clamp-2 text-small text-ink-tertiary">{summary}</p> : null}
    </Link>
  );
}
