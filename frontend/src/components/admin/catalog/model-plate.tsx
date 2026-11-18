"use client";

import type { Route } from "next";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { ResponsivePicture } from "@/components/ui/responsive-picture";
import { useListStock } from "@/lib/api/generated/admin-inventory/admin-inventory";
import type { ProductListItemOut, ProductStockOut } from "@/lib/api/generated/model";
import { formatPrice, formatProductNumber } from "@/lib/catalog/format";
import { readyPicture } from "@/lib/catalog/images";
import { PRODUCT_STATUS_LABELS } from "@/lib/catalog/labels";
import { formatShortDate } from "@/lib/format";
import { cn } from "@/lib/utils";

import { modelVariants } from "./model-stock";
import { useProduct, useReferences } from "./use-product";

type ModelPlateProps = {
  item: ProductListItemOut;
  stock: ProductStockOut | undefined;
  onEbay: boolean;
};

/**
 * The Typenschild of the Werkbank (ADR 0030): the chosen model at a glance beside the
 * list, with its photo, where it stands, what lies on the shelves per Ausführung and
 * where. Changing anything happens on the model's own page ("Bearbeiten").
 */
export function ModelPlate({ item, stock, onEbay }: ModelPlateProps) {
  const picture = readyPicture(item.main_image);
  const free = stock?.free ?? 0;
  const reserved = stock?.reserved ?? 0;
  const backordered = stock?.backordered ?? 0;
  const editHref = `/admin/modelle/${item.id}` as Route;
  const facts = [
    { label: "Frei im Regal", value: String(free), note: free === 0 ? "wird auf Bestellung gefertigt" : "sofort lieferbar" },
    { label: "Reserviert", value: String(reserved), note: "für bezahlte Bestellungen" },
    { label: "Zu fertigen", value: String(backordered), note: backordered === 0 ? "niemand wartet" : "bestellt, wartet auf die Werkstatt" },
    {
      label: "Preis ab",
      value: item.price_from_cents !== null ? formatPrice(item.price_from_cents) : "offen",
      note: item.variant_count === 1 ? "1 Ausführung" : `${item.variant_count} Ausführungen`,
    },
  ];
  const steps = [
    { name: "Foto", note: item.main_image ? "vorhanden" : "fehlt", state: item.main_image ? "done" : "missing" },
    { name: "Ausführungen", note: item.variant_count > 0 ? String(item.variant_count) : "fehlen", state: item.variant_count > 0 ? "done" : "missing" },
    {
      name: "Im Shop",
      note: item.status === "active" ? (item.published_at ? formatShortDate(new Date(item.published_at)) : "ja") : PRODUCT_STATUS_LABELS[item.status],
      state: item.status === "active" ? "done" : "open",
    },
    { name: "eBay", note: onEbay ? "aktiv" : "kein Angebot", state: onEbay ? "live" : "open" },
  ] as const;

  return (
    <article aria-label={`Typenschild ${item.name}`}>
      <div className="flex items-start gap-6">
        <span className="relative block size-36 shrink-0 overflow-hidden bg-surface">
          {picture ? (
            <ResponsivePicture image={picture} alt="" sizes="144px" fit="cover" />
          ) : (
            <span className="absolute inset-0 grid place-items-center text-hint text-ink-secondary">ohne Foto</span>
          )}
        </span>
        <div className="min-w-0 flex-1">
          <p className="label-caps text-ink-secondary">Typenschild · {formatProductNumber(item.number)}</p>
          <h2 className="mt-2.5 text-title break-words 2xl:text-display">{item.name}</h2>
          <ul className="mt-3.5 flex flex-wrap gap-2 text-hint">
            <li className={cn("px-2.5 py-1 font-semibold", item.status === "active" ? "bg-success text-on-selected" : "bg-sunken text-ink")}>
              {PRODUCT_STATUS_LABELS[item.status]}
            </li>
            {item.scale_codes.map((code) => (
              <li key={code} className="border border-ink px-2.5 py-1">
                {code}
              </li>
            ))}
            {onEbay ? <li className="border border-highlight px-2.5 py-1 text-accent">eBay</li> : null}
          </ul>
        </div>
      </div>
      <div className="mt-6 flex flex-wrap gap-2.5">
        <Button asChild className="shadow-hard transition-[transform,box-shadow,background-color,color] hover:translate-[3px] hover:shadow-hard-pressed">
          <Link href={editHref}>Bearbeiten</Link>
        </Button>
        {item.status === "active" ? (
          <Button asChild variant="secondary" className="border-ink">
            <Link href={`/produkte/${item.slug}` as Route} target="_blank">
              Im Shop ansehen
            </Link>
          </Button>
        ) : null}
      </div>

      <dl className="mt-7 grid grid-cols-2 gap-px border-[1.5px] border-ink bg-line 2xl:grid-cols-4">
        {facts.map((fact) => (
          <div key={fact.label} className="bg-canvas px-4 py-4">
            <dt className="label-caps text-ink-secondary">{fact.label}</dt>
            <dd className="mt-1.5 font-display text-[2.125rem] leading-[1.1] font-extrabold tabular-nums">{fact.value}</dd>
            <dd className="text-hint text-ink-secondary">{fact.note}</dd>
          </div>
        ))}
      </dl>

      <div className="mt-6 grid items-start gap-6 2xl:grid-cols-[1.1fr_1fr]">
        <VariantStock productId={item.id} editHref={editHref} />
        <section className="bg-surface px-5 py-5">
          <h3 className="text-[1.375rem] leading-7">Wo es liegt</h3>
          {stock && stock.places.length > 0 ? (
            <ul className="mt-2.5 text-small">
              {stock.places.map((place) => (
                <li key={place.code} className="flex justify-between gap-3 border-t border-line py-2">
                  <Link href={`/admin/lager/plaetze/${place.code}` as Route} className="min-w-0 truncate hover:underline hover:underline-offset-4">
                    {place.place}
                  </Link>
                  <span className="shrink-0 font-mono text-ink-secondary tabular-nums">{place.quantity} ×</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2.5 border-t border-line pt-3 text-small text-ink-secondary">Kein Stück im Regal.</p>
          )}
          {stock && stock.labeled > 0 ? (
            <p className="mt-3 text-small text-warning">{stock.labeled} mit Etikett, aber noch ohne Platz.</p>
          ) : null}
        </section>
      </div>

      <ol aria-label="Stand des Modells" className="mt-6 grid grid-cols-4 text-hint">
        {steps.map((step) => (
          <li
            key={step.name}
            className={cn(
              "border-t-4 pt-3",
              step.state === "done" ? "border-ink" : step.state === "live" ? "border-action" : step.state === "missing" ? "border-highlight" : "border-line-strong",
            )}
          >
            <span className="block font-semibold">{step.name}</span>
            <span className="block font-mono text-ink-secondary">{step.note}</span>
          </li>
        ))}
      </ol>
    </article>
  );
}

/** Free pieces per Ausführung as bars, the fullest shelf setting the scale. */
function VariantStock({ productId, editHref }: { productId: string; editHref: Route }) {
  const product = useProduct(productId);
  const references = useReferences();
  const stock = useListStock({
    query: { select: (data) => new Map(data.items.map((line) => [line.variant_id, line])) },
  });
  const variants = product.data && references.data ? modelVariants(product.data, references.data) : [];
  const freeOf = (variantId: string) => stock.data?.get(variantId)?.in_stock ?? 0;
  const most = Math.max(1, ...variants.map(({ variant }) => freeOf(variant.id)));
  return (
    <section className="bg-surface px-5 py-5">
      <h3 className="text-[1.375rem] leading-7">Bestand je Ausführung</h3>
      {product.isPending || references.isPending ? (
        <p className="mt-3 text-small text-ink-secondary">Wird geladen …</p>
      ) : variants.length === 0 ? (
        <p className="mt-3 text-small text-ink-secondary">Noch keine Ausführung, also auch keine Stücke.</p>
      ) : (
        <ul className="mt-1">
          {variants.map(({ variant, name }) => {
            const free = freeOf(variant.id);
            return (
              <li key={variant.id} className="mt-3.5 grid grid-cols-[minmax(0,11rem)_minmax(0,1fr)_2.5rem] items-center gap-3 text-small">
                <span className="truncate" title={name}>
                  {name}
                </span>
                <span aria-hidden="true" className="block h-3.5 bg-sunken">
                  <span
                    className={cn("block h-full transition-[width] duration-500 motion-reduce:transition-none", free > 0 ? "bg-action" : "bg-highlight")}
                    style={{ width: free > 0 ? `${(free / most) * 100}%` : "3px" }}
                  />
                </span>
                <b className="text-right font-mono font-medium tabular-nums">{free}</b>
              </li>
            );
          })}
        </ul>
      )}
      <p className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3.5 text-small">
        <span className="text-ink-secondary">Einbuchen, ausbuchen, umlagern:</span>
        <Link href={editHref} className="font-semibold text-accent hover:underline hover:underline-offset-4">
          Zum Bestand
        </Link>
      </p>
    </section>
  );
}
