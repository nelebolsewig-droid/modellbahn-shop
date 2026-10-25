import Link from "next/link";
import type { Route } from "next";

import { formatPrice } from "@/lib/catalog/format";

import { ResponsivePicture, type PictureImage } from "./responsive-picture";
import { SpecLine } from "./spec-line";

type ProductCardProps = {
  href: Route;
  name: string;
  summary: string;
  /** Scales for sale, by name, e.g. ["H0", "1:24"]. */
  scales: readonly string[];
  priceFromCents: number | null;
  image: PictureImage | null;
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
  image,
  priority = false,
}: ProductCardProps) {
  return (
    <Link href={href} className="group block rounded-md">
      <div className="relative aspect-square rounded-md bg-stage transition-colors duration-150 group-hover:bg-sunken">
        {image ? (
          <div className="absolute inset-6">
            <ResponsivePicture
              image={image}
              alt=""
              sizes="(min-width: 1024px) 30vw, (min-width: 640px) 45vw, 90vw"
              priority={priority}
            />
          </div>
        ) : (
          <p className="absolute inset-0 flex items-center justify-center label-caps text-ink-tertiary">
            Foto folgt
          </p>
        )}
      </div>
      <div className="mt-4 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="text-[1.125rem] leading-6 font-normal tracking-[-0.01em] group-hover:underline group-hover:underline-offset-4">
            {name}
          </h3>
          {scales.length > 0 ? <SpecLine values={scales} size="small" className="mt-1" /> : null}
        </div>
        {priceFromCents !== null ? (
          <p className="shrink-0 text-small text-ink-secondary tabular-nums">
            ab {formatPrice(priceFromCents)}
          </p>
        ) : null}
      </div>
      {summary ? <p className="mt-2 line-clamp-2 text-small text-ink-tertiary">{summary}</p> : null}
    </Link>
  );
}
