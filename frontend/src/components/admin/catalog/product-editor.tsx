"use client";

import { useQueryClient } from "@tanstack/react-query";
import type { Route } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { ConnectionLamp } from "@/components/admin/connection-lamp";
import { ProductBomPanel } from "@/components/admin/manufacturing/bom-panel";
import { ProductEbayPanel } from "@/components/admin/marketplace/product-ebay-panel";
import { Panel } from "@/components/admin/panel";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { PendingNotice } from "@/components/ui/pending-notice";
import { ResponsivePicture } from "@/components/ui/responsive-picture";
import { StatusBadge } from "@/components/ui/status-badge";
import { archiveProduct, publishProduct } from "@/lib/api/generated/admin-catalog/admin-catalog";
import { getListStockQueryKey } from "@/lib/api/generated/admin-inventory/admin-inventory";
import type { ProductOut } from "@/lib/api/generated/model";
import { formatPrice, formatProductNumber } from "@/lib/catalog/format";
import { readyPicture } from "@/lib/catalog/images";
import { PRODUCT_STATUS_LABELS, PUBLISH_BLOCKER_LABELS, PUBLISH_RULES } from "@/lib/catalog/labels";
import { ifMatch } from "@/lib/catalog/versions";
import { formatEventTime } from "@/lib/format";
import { errorMessage } from "@/lib/i18n/problems";
import { ADMIN_EVENTS_URL, assetIdOf, INVENTORY_EVENT_TYPES, MEDIA_EVENT_TYPES, stockEventOf } from "@/lib/realtime/events";
import { useEventStream } from "@/lib/realtime/use-event-stream";

import { DeleteProduct } from "./delete-product";
import { STATUS_TONES } from "./product-list";
import { ProductDetailsForm } from "./product-details-form";
import { ProductGallery } from "./product-gallery";
import { ProductScales } from "./product-scales";
import { ModelHistory, ModelStock } from "./model-stock";
import {
  isVersionConflict,
  productQueryKey,
  useCategories,
  useProduct,
  useProductCommand,
  useReferences,
} from "./use-product";

type ProductEditorProps = { productId: string; onStreamClosed: () => void };

/**
 * One model (ADR 0028): what it is and where it stands at the top, its stock with the
 * day's actions, the editor's sections closed below, and its history at the end.
 */
export function ProductEditor({ productId, onStreamClosed }: ProductEditorProps) {
  const queryClient = useQueryClient();
  const product = useProduct(productId);
  const references = useReferences();
  const categories = useCategories();
  const mediaIds = new Set(product.data?.media.map((item) => item.asset_id) ?? []);
  const variantIds = new Set(product.data?.scales.flatMap((scale) => scale.variants.map((variant) => variant.id)) ?? []);

  // A processed photo swaps its placeholder for the thumbnail without reloading; the
  // stock of the Ausführungen follows the store.
  const stream = useEventStream({
    url: ADMIN_EVENTS_URL,
    eventTypes: [...MEDIA_EVENT_TYPES, ...INVENTORY_EVENT_TYPES],
    onMessage(data) {
      const assetId = assetIdOf(data);
      if (assetId !== null && mediaIds.has(assetId)) {
        void queryClient.invalidateQueries({ queryKey: productQueryKey(productId) });
      }
      const stock = stockEventOf(data);
      if (stock?.variantId && variantIds.has(stock.variantId)) {
        void queryClient.invalidateQueries({ queryKey: getListStockQueryKey() });
      }
    },
    onClosed: onStreamClosed,
  });

  if (product.isPending || references.isPending || categories.isPending) {
    return <PendingNotice>Das Modell wird geladen …</PendingNotice>;
  }
  const failure = product.error ?? references.error ?? categories.error;
  if (failure || !product.data || !references.data || !categories.data) {
    return (
      <div className="space-y-4">
        <Alert tone="danger" title="Das Modell konnte nicht geladen werden">
          <p>{errorMessage(failure)}</p>
        </Alert>
        <Button asChild variant="secondary">
          <Link href="/admin/modelle">Zurück zu den Modellen</Link>
        </Button>
      </div>
    );
  }

  const data = product.data;
  return (
    <div className="space-y-6">
      <EditorHeader product={data} stream={<ConnectionLamp state={stream.state} onReconnect={stream.reconnect} />} />
      <ModelStock product={data} references={references.data} />
      <div className="space-y-3">
        <Section title="Fotos">
          <ProductGallery product={data} references={references.data} />
        </Section>
        <Section title="Maßstäbe, Ausführungen und Preise">
          <ProductScales product={data} references={references.data} />
        </Section>
        <Section title="Beschreibung und Kategorie">
          <ProductDetailsForm product={data} categories={categories.data} epochs={references.data.epochs} />
        </Section>
        <Section title="Shop: veröffentlichen, archivieren, löschen">
          <PublishPanel product={data} />
        </Section>
        <Section title="eBay">
          <ProductEbayPanel product={data} />
        </Section>
        <Section title="Stückliste für die Fertigung">
          <ProductBomPanel product={data} />
        </Section>
      </div>
      <ModelHistory productId={data.id} />
    </div>
  );
}

/** An editor section, closed until someone needs it. */
function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <details className="group rounded-md border border-line bg-surface">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-5 py-4 font-medium">
        {title}
        <span aria-hidden="true" className="text-ink-tertiary transition-transform group-open:rotate-90">
          ›
        </span>
      </summary>
      <div className="border-t border-line p-3 sm:p-5">{children}</div>
    </details>
  );
}

function EditorHeader({ product, stream }: { product: ProductOut; stream: ReactNode }) {
  // The first picture of the gallery is the model's main picture, as in the shop.
  const main = [...product.media].sort((a, b) => a.position - b.position)[0];
  const picture = readyPicture(main?.image);
  const prices = product.scales.flatMap((scale) => scale.variants.map((variant) => variant.price_cents)).filter((cents) => cents > 0);
  const lowest = prices.length > 0 ? Math.min(...prices) : null;
  return (
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div className="flex min-w-0 items-start gap-5">
        <span className="relative block size-24 shrink-0 overflow-hidden rounded-md bg-stage sm:size-28">
          {picture ? (
            <ResponsivePicture image={picture} alt="" sizes="112px" variant="thumb" fit="cover" />
          ) : (
            <span className="absolute inset-0 flex items-center justify-center text-hint text-ink-tertiary">ohne Foto</span>
          )}
        </span>
        <div className="min-w-0">
          <Link href="/admin/modelle" className="text-hint text-ink-tertiary hover:text-ink">
            ← Modelle
          </Link>
          <h1 className="mt-2 text-heading break-words sm:text-title">{product.name}</h1>
          <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-small">
            <StatusBadge tone={STATUS_TONES[product.status]}>{PRODUCT_STATUS_LABELS[product.status]}</StatusBadge>
            {lowest !== null ? (
              <span className="tabular-nums">
                {prices.some((cents) => cents !== lowest) ? "ab " : ""}
                {formatPrice(lowest)}
              </span>
            ) : null}
            <span className="font-mono text-hint text-ink-tertiary">{formatProductNumber(product.number)}</span>
            <span className="text-hint text-ink-tertiary">geändert {formatEventTime(new Date(product.updated_at))}</span>
          </p>
          {product.status === "active" ? (
            <Button asChild size="sm" variant="secondary" className="mt-3">
              <Link href={`/produkte/${product.slug}` as Route} target="_blank" rel="noopener">
                Im Shop ansehen
              </Link>
            </Button>
          ) : null}
        </div>
      </div>
      {stream}
    </header>
  );
}

function PublishPanel({ product }: { product: ProductOut }) {
  const queryClient = useQueryClient();
  const command = useProductCommand(product.id);
  const blockers = new Set(product.publish_blockers);
  const conflict = isVersionConflict(command.error);
  const error = command.error;

  return (
    <Panel title={product.status === "active" ? "Im Shop" : "Veröffentlichen"}>
      <ul aria-label="Regeln für den Shop" className="space-y-2">
        {PUBLISH_RULES.map((rule) => {
          const met = !blockers.has(rule);
          return (
            <li key={rule} className="flex items-start gap-3 text-small">
              <span
                aria-hidden="true"
                className={
                  met
                    ? "mt-1 size-3 shrink-0 rounded-full bg-success"
                    : "mt-1 size-3 shrink-0 rounded-full ring-1 ring-line-control ring-inset"
                }
              />
              <span className={met ? "text-ink" : "text-ink-secondary"}>
                {PUBLISH_BLOCKER_LABELS[rule]}
                <span className="sr-only">{met ? " (erfüllt)" : " (fehlt noch)"}</span>
              </span>
            </li>
          );
        })}
      </ul>

      <div className="mt-6 flex flex-col gap-2">
        {product.status !== "active" ? (
          <Button
            type="button"
            disabled={blockers.size > 0 || command.isPending}
            aria-busy={command.isPending || undefined}
            onClick={() => command.mutate(() => publishProduct(product.id, ifMatch(product.version)))}
          >
            {product.status === "archived" ? "Wieder in den Shop" : "Veröffentlichen"}
          </Button>
        ) : (
          <>
            <Button asChild variant="secondary">
              <Link href={`/produkte/${product.slug}` as Route} target="_blank" rel="noopener">
                Im Shop ansehen
              </Link>
            </Button>
            <Button
              type="button"
              variant="secondary"
              disabled={command.isPending}
              onClick={() => command.mutate(() => archiveProduct(product.id, ifMatch(product.version)))}
            >
              Archivieren
            </Button>
          </>
        )}
        <DeleteProduct product={product} />
      </div>
      {blockers.size > 0 && product.status !== "active" ? (
        <p className="mt-3 text-hint text-ink-tertiary">Veröffentlichen geht, sobald alle Punkte erfüllt sind.</p>
      ) : null}
      <div role="alert" className="not-empty:mt-4">
        {error ? (
          <Alert tone="danger" title={conflict ? "Inzwischen geändert" : "Das hat nicht geklappt"}>
            <p>{errorMessage(error)}</p>
            {conflict ? (
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => {
                  command.reset();
                  void queryClient.invalidateQueries({ queryKey: productQueryKey(product.id) });
                }}
              >
                Aktuellen Stand laden
              </Button>
            ) : null}
          </Alert>
        ) : null}
      </div>
    </Panel>
  );
}
