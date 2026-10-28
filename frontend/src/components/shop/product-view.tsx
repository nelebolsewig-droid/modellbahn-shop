"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { AddToCart } from "@/components/shop/add-to-cart";
import { OptionGroup, OptionPill } from "@/components/ui/option-pill";
import { ProductStage, type StageItem } from "@/components/ui/product-stage";
import { RadioGroup } from "@/components/ui/radio-group";
import { ScaleTile } from "@/components/ui/scale-tile";
import { SpecLine } from "@/components/ui/spec-line";
import { useGetProductAvailability } from "@/lib/api/generated/store-inventory/store-inventory";
import type { StoreGalleryItemOut, StoreProductOut } from "@/lib/api/generated/model";
import {
  dimensionsLine,
  formatGrams,
  formatMillimetres,
  formatPrice,
  formatProductNumber,
} from "@/lib/catalog/format";
import { scaleLabel } from "@/lib/catalog/scales";
import { cn } from "@/lib/utils";

type Selection = { scale: string; finish: string };

/** Photos of the chosen scale and finish first, then untagged ones, then the others. */
export function galleryFor(gallery: readonly StoreGalleryItemOut[], selection: Selection): StageItem[] {
  const score = (tag: string | null, chosen: string) => (tag === chosen ? 0 : tag === null ? 1 : 2);
  return gallery
    .map((item, position) => ({ item, position }))
    .sort(
      (a, b) =>
        score(a.item.scale_code, selection.scale) + score(a.item.finish_code, selection.finish) -
          (score(b.item.scale_code, selection.scale) + score(b.item.finish_code, selection.finish)) ||
        a.position - b.position,
    )
    .map(({ item }) => ({ key: item.image.asset_id, image: item.image, alt: item.alt_text }));
}

function initialSelection(product: StoreProductOut, scaleCode: string | undefined): Selection {
  const scale = product.scales.find((s) => s.code === scaleCode) ?? product.scales[0];
  return { scale: scale?.code ?? "", finish: scale?.variants[0]?.finish_code ?? "" };
}

type ProductViewProps = {
  product: StoreProductOut;
  /** The scale to open with, e.g. the one of the list the visitor came from. */
  initialScale?: string;
};

/**
 * The upper part of a product page: the photo stage on the left, the choice of
 * scale and finish with price, quantity and "In den Warenkorb" on the right.
 */
export function ProductView({ product, initialScale }: ProductViewProps) {
  const [selection, setSelection] = useState<Selection>(() => initialSelection(product, initialScale));
  const scale = product.scales.find((s) => s.code === selection.scale) ?? product.scales[0];
  const variant = scale?.variants.find((v) => v.finish_code === selection.finish) ?? scale?.variants[0];
  const finish = product.finishes.find((f) => f.code === variant?.finish_code);
  const items = useMemo(() => galleryFor(product.gallery, selection), [product.gallery, selection]);
  // Stock changes by the minute, so it is fetched live; the page itself stays cached.
  const availability = useGetProductAvailability(product.slug, { query: { refetchOnWindowFocus: true } });
  // German compounds ("Löschgruppenfahrzeug") do not fit the column in display size.
  const longWord = product.name.split(/\s+/).some((word) => word.length > 14);

  function chooseScale(code: string) {
    const next = product.scales.find((s) => s.code === code);
    // Keep the finish if the new scale has it, otherwise take its first one.
    const keeps = next?.variants.some((v) => v.finish_code === selection.finish) ?? false;
    setSelection({ scale: code, finish: keeps ? selection.finish : (next?.variants[0]?.finish_code ?? "") });
  }

  return (
    <div className="grid items-start gap-10 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] lg:gap-16">
      {/* A new selection starts the stage at its best matching photo. */}
      <ProductStage key={`${selection.scale}-${selection.finish}`} items={items} aspect="4/5" />

      <div className="lg:sticky lg:top-8">
        <p className="font-mono text-hint text-ink-tertiary">{formatProductNumber(product.number)}</p>
        <h1 className={cn("mt-3 text-title hyphens-auto break-words", !longWord && "sm:text-display")}>{product.name}</h1>
        {scale ? (
          <SpecLine values={[scaleLabel(scale), ...(finish ? [finish.name] : [])]} className="mt-4" />
        ) : null}
        {product.summary ? <p className="mt-5 text-body-lg text-ink-secondary">{product.summary}</p> : null}

        {scale && variant ? (
          <div className="mt-10 space-y-8">
            <div>
              <p className="label-caps text-ink-tertiary" aria-hidden="true">
                Maßstab
              </p>
              <RadioGroup
                aria-label="Maßstab"
                value={selection.scale}
                onValueChange={chooseScale}
                className="mt-3 flex flex-wrap gap-3"
              >
                {product.scales.map((option) => (
                  <ScaleTile
                    key={option.code}
                    value={option.code}
                    name={option.name}
                    spec={[
                      ...(option.name === option.ratio ? [] : [option.ratio]),
                      option.track_gauge_mm === null ? "ohne Gleis" : `Gleis ${formatMillimetres(option.track_gauge_mm)}`,
                    ]}
                    note={`ab ${formatPrice(Math.min(...option.variants.map((v) => v.price_cents)))}`}
                  />
                ))}
              </RadioGroup>
            </div>

            <OptionGroup
              label="Ausführung"
              aside={finish?.name}
              value={variant.finish_code}
              onValueChange={(code) => setSelection({ ...selection, finish: code })}
            >
              {product.finishes.map((option) => {
                const offered = scale.variants.some((v) => v.finish_code === option.code);
                return (
                  <OptionPill
                    key={option.code}
                    value={option.code}
                    disabled={!offered}
                    unavailable={!offered}
                    aria-label={offered ? option.name : `${option.name} (in ${scale.name} nicht erhältlich)`}
                  >
                    {option.name}
                  </OptionPill>
                );
              })}
            </OptionGroup>

            <div className="border-t border-line pt-8">
              <p className="flex items-baseline gap-3">
                <span className="text-heading tabular-nums">{formatPrice(variant.price_cents)}</span>
                {variant.compare_at_price_cents !== null ? (
                  <s className="text-ink-tertiary tabular-nums">
                    <span className="sr-only">statt </span>
                    {formatPrice(variant.compare_at_price_cents)}
                  </s>
                ) : null}
              </p>
              <p className="mt-1 text-hint text-ink-tertiary">
                inkl. MwSt., zzgl.{" "}
                <Link href="/versand" className="underline underline-offset-4 hover:text-ink">
                  Versand
                </Link>
              </p>
              <div className="mt-6">
                {/* A new selection starts with quantity 1 and without the last confirmation. */}
                <AddToCart
                  key={variant.id}
                  variantId={variant.id}
                  title={[product.name, scale.name, ...(finish ? [finish.name] : [])].join(" · ")}
                  availability={availability.data?.items.find((item) => item.variant_id === variant.id)}
                />
              </div>
            </div>

            <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-6 gap-y-2 border-t border-line pt-8 text-small">
              <dt className="text-ink-tertiary">Artikelnummer</dt>
              <dd className="font-mono">{variant.sku}</dd>
              {dimensionsLine(scale).length > 0 ? (
                <>
                  <dt className="text-ink-tertiary">Maße in {scale.name}</dt>
                  <dd>{dimensionsLine(scale).join(" · ")}</dd>
                </>
              ) : null}
              {scale.weight_g !== null ? (
                <>
                  <dt className="text-ink-tertiary">Gewicht</dt>
                  <dd>{formatGrams(scale.weight_g)}</dd>
                </>
              ) : null}
            </dl>
          </div>
        ) : null}
      </div>
    </div>
  );
}
