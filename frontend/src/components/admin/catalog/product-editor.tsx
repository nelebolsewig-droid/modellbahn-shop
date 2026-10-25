"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { Route } from "next";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";

import { ConnectionLamp } from "@/components/admin/connection-lamp";
import { Panel } from "@/components/admin/panel";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { PendingNotice } from "@/components/ui/pending-notice";
import { StatusBadge } from "@/components/ui/status-badge";
import { archiveProduct, deleteProduct, publishProduct } from "@/lib/api/generated/admin-catalog/admin-catalog";
import type { ProductOut } from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";
import { formatProductNumber } from "@/lib/catalog/format";
import { PRODUCT_STATUS_LABELS, PUBLISH_BLOCKER_LABELS, PUBLISH_RULES } from "@/lib/catalog/labels";
import { ifMatch } from "@/lib/catalog/versions";
import { formatEventTime } from "@/lib/format";
import { errorMessage } from "@/lib/i18n/problems";
import { ADMIN_EVENTS_URL, assetIdOf, MEDIA_EVENT_TYPES } from "@/lib/realtime/events";
import { useEventStream } from "@/lib/realtime/use-event-stream";

import { STATUS_TONES } from "./product-list";
import { ProductDetailsForm } from "./product-details-form";
import { ProductGallery } from "./product-gallery";
import { ProductScales } from "./product-scales";
import {
  ADMIN_PRODUCTS_KEY,
  isVersionConflict,
  productQueryKey,
  useCategories,
  useProduct,
  useProductCommand,
  useReferences,
} from "./use-product";

type ProductEditorProps = { productId: string; onStreamClosed: () => void };

/** Everything about one product: master data, scales and variants, gallery, life cycle. */
export function ProductEditor({ productId, onStreamClosed }: ProductEditorProps) {
  const queryClient = useQueryClient();
  const product = useProduct(productId);
  const references = useReferences();
  const categories = useCategories();
  const mediaIds = new Set(product.data?.media.map((item) => item.asset_id) ?? []);

  // A processed photo swaps its placeholder for the thumbnail without reloading.
  const stream = useEventStream({
    url: ADMIN_EVENTS_URL,
    eventTypes: MEDIA_EVENT_TYPES,
    onMessage(data) {
      const assetId = assetIdOf(data);
      if (assetId !== null && mediaIds.has(assetId)) {
        void queryClient.invalidateQueries({ queryKey: productQueryKey(productId) });
      }
    },
    onClosed: onStreamClosed,
  });

  if (product.isPending || references.isPending || categories.isPending) {
    return <PendingNotice>Das Produkt wird geladen …</PendingNotice>;
  }
  const failure = product.error ?? references.error ?? categories.error;
  if (failure || !product.data || !references.data || !categories.data) {
    return (
      <div className="space-y-4">
        <Alert tone="danger" title="Das Produkt konnte nicht geladen werden">
          <p>{errorMessage(failure)}</p>
        </Alert>
        <Button asChild variant="secondary">
          <Link href="/admin/katalog">Zurück zum Katalog</Link>
        </Button>
      </div>
    );
  }

  const data = product.data;
  return (
    <div className="space-y-6">
      <EditorHeader product={data} stream={<ConnectionLamp state={stream.state} onReconnect={stream.reconnect} />} />
      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-6">
          <ProductGallery product={data} references={references.data} />
          <ProductScales product={data} references={references.data} />
          <ProductDetailsForm product={data} categories={categories.data} epochs={references.data.epochs} />
        </div>
        <PublishPanel product={data} />
      </div>
    </div>
  );
}

function EditorHeader({ product, stream }: { product: ProductOut; stream: ReactNode }) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <Link href="/admin/katalog" className="text-hint text-ink-tertiary hover:text-ink">
          ← Katalog
        </Link>
        <h1 className="mt-3 text-heading break-words sm:text-title">{product.name}</h1>
        <p className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-hint text-ink-tertiary">
          <span>{formatProductNumber(product.number)}</span>
          <StatusBadge tone={STATUS_TONES[product.status]}>{PRODUCT_STATUS_LABELS[product.status]}</StatusBadge>
          <span>Version {product.version}</span>
          <span>geändert {formatEventTime(new Date(product.updated_at))}</span>
        </p>
      </div>
      {stream}
    </header>
  );
}

function PublishPanel({ product }: { product: ProductOut }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const command = useProductCommand(product.id);
  const remove = useMutation<void, ApiProblem>({
    mutationFn: () => deleteProduct(product.id, ifMatch(product.version)),
    onSuccess() {
      void queryClient.invalidateQueries({ queryKey: ADMIN_PRODUCTS_KEY });
      router.replace("/admin/katalog");
    },
  });
  const blockers = new Set(product.publish_blockers);
  const deletable = product.status === "draft" && product.published_at === null;
  const conflict = isVersionConflict(command.error) || isVersionConflict(remove.error);
  const error = command.error ?? remove.error;

  return (
    <Panel title={product.status === "active" ? "Im Shop" : "Veröffentlichen"} code="PRD 01">
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
        {deletable ? (
          <Button
            type="button"
            variant="ghost"
            disabled={remove.isPending}
            onClick={() => {
              if (window.confirm(`Den Entwurf „${product.name}“ endgültig löschen?`)) {
                remove.mutate();
              }
            }}
          >
            Entwurf löschen
          </Button>
        ) : null}
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
                  remove.reset();
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
