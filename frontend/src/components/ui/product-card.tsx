import Link from "next/link";
import type { Route } from "next";

import { formatPrice } from "@/lib/catalog/format";

import { ModelPhoto } from "./model-photo";
import type { PictureImage } from "./responsive-picture";
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
    <Link
      href={href}
      className="group block rounded-lg border border-line bg-surface p-2.5 pb-5 transition-[transform,box-shadow,border-color] duration-300 ease-settle hover:-translate-y-1.5 hover:border-transparent hover:shadow-lift"
    >
      <div className="relative aspect-square rounded-md bg-stage">
        {image ? (
          <ModelPhoto
            image={image}
            alt=""
            sizes="(min-width: 1024px) 30vw, (min-width: 640px) 45vw, 90vw"
            priority={priority}
            zoom
          />
        ) : (
          <p className="absolute inset-0 flex items-center justify-center label-caps text-ink-tertiary">
            Foto folgt
          </p>
        )}
        {/* An arrow in signal orange slides in under the pointer; the card itself is the link. */}
        <span
          aria-hidden="true"
          className="absolute right-3 bottom-3 grid size-10 translate-y-2 place-items-center rounded-full bg-blaze text-on-highlight opacity-0 transition-[opacity,transform] duration-300 ease-settle group-hover:translate-y-0 group-hover:opacity-100"
        >
          →
        </span>
      </div>
      {/* The name has the whole width; scales and price share the line below. */}
      <div className="px-2.5">
      <h3 className="mt-4 text-[1.125rem] leading-6 font-semibold tracking-[-0.01em] hyphens-auto break-words transition-colors duration-150 group-hover:text-highlight-ink">
        {name}
      </h3>
      <div className="mt-1 flex items-baseline justify-between gap-4">
        {scales.length > 0 ? <SpecLine values={scales} size="small" /> : <span />}
        {priceFromCents !== null ? (
          <p className="shrink-0 rounded-full bg-sun px-2.5 py-0.5 text-small font-semibold text-ink tabular-nums">
            ab {formatPrice(priceFromCents)}
          </p>
        ) : null}
      </div>
      {summary ? <p className="mt-2 line-clamp-2 text-small text-ink-tertiary">{summary}</p> : null}
      </div>
    </Link>
  );
}
