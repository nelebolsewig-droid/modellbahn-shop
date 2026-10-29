"use client";

import { useMutation } from "@tanstack/react-query";
import type { Route } from "next";
import Link from "next/link";

import { Panel } from "@/components/admin/panel";
import { PendingNotice } from "@/components/ui/pending-notice";
import { setProductEbayListing } from "@/lib/api/generated/admin-marketplace/admin-marketplace";
import type { ListingOut, ProductOut } from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";
import { errorMessage } from "@/lib/i18n/problems";
import { isReady, MODE_LABELS } from "@/lib/marketplace/labels";

import { ListingRow } from "./ebay-desk";
import { useEbayRefresh, useEbayStatus, useProductListings } from "./use-ebay";

/**
 * "Auf eBay anbieten" in the product editor: one switch per scale. The worker brings
 * the offer up within a minute; prices, stock and texts follow the shop by themselves.
 */
export function ProductEbayPanel({ product }: { product: ProductOut }) {
  const status = useEbayStatus();
  const on = status.data !== undefined && status.data.mode !== "off";
  const listings = useProductListings(product.id, on);
  if (!on) {
    return null;
  }
  const ready = isReady(status.data);
  return (
    <Panel
      title="eBay"
      code="PRD 02"
      actions={<span className="text-hint text-ink-tertiary">{MODE_LABELS[status.data.mode]}</span>}
    >
      {product.scales.length === 0 ? (
        <p className="text-small text-ink-secondary">Leg zuerst einen Maßstab mit Varianten an.</p>
      ) : listings.isPending ? (
        <PendingNotice>eBay-Angebote werden geladen …</PendingNotice>
      ) : listings.isError ? (
        <p role="alert" className="text-small text-danger">
          {errorMessage(listings.error)}
        </p>
      ) : (
        <ul className="divide-y divide-line">
          {product.scales.map((scale) => (
            <ScaleOffer
              key={scale.scale_code}
              productId={product.id}
              scaleCode={scale.scale_code}
              listing={listings.data.find((listing) => listing.scale_code === scale.scale_code) ?? null}
              canSync={ready}
            />
          ))}
        </ul>
      )}
      {!ready ? (
        <p className="mt-3 text-hint text-ink-tertiary">
          Angebote gehen online, sobald eBay eingerichtet ist:{" "}
          <Link href={"/admin/ebay" as Route} className="text-accent hover:underline">
            zur eBay-Seite
          </Link>
          .
        </p>
      ) : null}
    </Panel>
  );
}

function ScaleOffer({
  productId,
  scaleCode,
  listing,
  canSync,
}: {
  productId: string;
  scaleCode: string;
  listing: ListingOut | null;
  canSync: boolean;
}) {
  const refresh = useEbayRefresh();
  const want = useMutation<ListingOut, ApiProblem, boolean>({
    mutationFn: (wanted) => setProductEbayListing(productId, scaleCode, { wanted }),
    onSettled: refresh,
  });
  const wanted = want.isPending ? want.variables : (listing?.wanted ?? false);
  const id = `ebay-${productId}-${scaleCode}`;
  return (
    <li className="py-3 first:pt-0 last:pb-0">
      <div className="flex items-center justify-between gap-3">
        <label htmlFor={id} className="text-small font-medium">
          {`Auf eBay anbieten · ${scaleCode}`}
        </label>
        <input
          id={id}
          type="checkbox"
          role="switch"
          className="size-5 cursor-pointer accent-[var(--selected)]"
          checked={wanted}
          disabled={want.isPending}
          // Read the new state now: React resets a controlled checkbox before a later read.
          onChange={(event) => want.mutate(event.currentTarget.checked)}
        />
      </div>
      {want.isError ? (
        <p role="alert" className="mt-1 text-hint text-danger">
          {errorMessage(want.error)}
        </p>
      ) : null}
      {listing ? (
        <ul>
          <ListingRow listing={listing} canSync={canSync} compact />
        </ul>
      ) : null}
    </li>
  );
}
