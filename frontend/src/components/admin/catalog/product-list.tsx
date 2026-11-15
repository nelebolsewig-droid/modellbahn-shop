"use client";

import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type { Route } from "next";
import Link from "next/link";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { OptionGroup, OptionPill } from "@/components/ui/option-pill";
import { PendingNotice } from "@/components/ui/pending-notice";
import { ResponsivePicture } from "@/components/ui/responsive-picture";
import { StatusBadge } from "@/components/ui/status-badge";
import { listProducts, publishReadyProducts } from "@/lib/api/generated/admin-catalog/admin-catalog";
import { useListProductStock } from "@/lib/api/generated/admin-inventory/admin-inventory";
import { useListEbayListings } from "@/lib/api/generated/admin-marketplace/admin-marketplace";
import type {
  ProductListItemOut,
  ProductPageOut,
  ProductStatus,
  ProductStockOut,
  PublishedOut,
} from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";
import { formatPrice, formatProductNumber } from "@/lib/catalog/format";
import { readyPicture } from "@/lib/catalog/images";
import { PRODUCT_STATUS_LABELS } from "@/lib/catalog/labels";
import { placesLine } from "@/lib/inventory/stock";
import { errorMessage } from "@/lib/i18n/problems";

import { ADMIN_PRODUCTS_KEY } from "./use-product";

const PAGE_SIZE = 50;

type Filter = "all" | "draft" | "empty";

const FILTERS: readonly { value: Filter; label: string }[] = [
  { value: "all", label: "Alle" },
  { value: "draft", label: "Entwürfe" },
  { value: "empty", label: "Ohne Bestand" },
];

export const STATUS_TONES = {
  draft: "neutral",
  active: "success",
  archived: "warning",
} as const satisfies Record<ProductStatus, "neutral" | "success" | "warning">;

/** Models without a free or reserved piece; nothing at all counts as none. */
export function withoutStock(item: ProductListItemOut, stock: ReadonlyMap<string, ProductStockOut>): boolean {
  const line = stock.get(item.id);
  return line === undefined || line.free + line.reserved === 0;
}

/**
 * Every model, newest first: photo, name, where it stands (shop, draft, archive, eBay),
 * how many pieces are free or reserved and where they lie. A tap opens the model.
 */
export function ProductList() {
  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const products = useInfiniteQuery<ProductPageOut, ApiProblem>({
    queryKey: [...ADMIN_PRODUCTS_KEY, { status: filter === "draft" ? "draft" : null, query }],
    queryFn: ({ pageParam, signal }) =>
      listProducts(
        {
          limit: PAGE_SIZE,
          ...(filter === "draft" && { status: "draft" as const }),
          ...(query && { q: query }),
          ...(typeof pageParam === "string" && { cursor: pageParam }),
        },
        { signal },
      ),
    initialPageParam: null,
    getNextPageParam: (page) => page.next_cursor,
  });
  const stock = useListProductStock({
    query: { select: (data) => new Map(data.items.map((line) => [line.product_id, line])) },
  });
  // eBay may not be connected: then no model shows the mark, and nothing complains.
  const ebay = useListEbayListings(
    { limit: 100 },
    {
      query: {
        retry: false,
        select: (page) => new Set(page.items.filter((listing) => listing.status === "active").map((listing) => listing.product_id)),
      },
    },
  );
  const stockByProduct = stock.data ?? new Map<string, ProductStockOut>();
  const all = products.data?.pages.flatMap((page) => page.items) ?? [];
  const items = filter === "empty" ? all.filter((item) => withoutStock(item, stockByProduct)) : all;

  function onSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setQuery(search.trim());
  }

  return (
    <section aria-label="Modelle">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <OptionGroup label="Zeigen" value={filter} onValueChange={(value) => setFilter(value as Filter)}>
          {FILTERS.map((entry) => (
            <OptionPill key={entry.value} value={entry.value} tone="accent">
              {entry.label}
            </OptionPill>
          ))}
        </OptionGroup>
        <form role="search" onSubmit={onSearch} className="flex w-full items-center gap-2 sm:w-auto">
          <label htmlFor="model-search" className="sr-only">
            Modell suchen
          </label>
          <Input
            id="model-search"
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Name oder Nummer"
            className="sm:w-64"
          />
          <Button type="submit" variant="secondary">
            Suchen
          </Button>
        </form>
      </div>
      {filter === "draft" ? <PublishReady /> : null}

      <div className="mt-6">
        {products.isPending ? (
          <PendingNotice>Modelle werden geladen …</PendingNotice>
        ) : products.isError ? (
          <p role="alert" className="text-small text-danger">
            {errorMessage(products.error)}
          </p>
        ) : items.length === 0 ? (
          <p className="rounded-md border border-dashed border-line-strong px-5 py-10 text-center text-small text-ink-secondary">
            {query || filter !== "all" ? "Keine Modelle für diese Auswahl." : "Noch kein Modell. Mit „Neues Modell“ geht es los."}
          </p>
        ) : (
          <ul className="divide-y divide-line border-y border-line">
            {items.map((item) => (
              <ProductRow key={item.id} item={item} stock={stockByProduct.get(item.id)} onEbay={ebay.data?.has(item.id) ?? false} />
            ))}
          </ul>
        )}
        {products.hasNextPage ? (
          <Button
            type="button"
            variant="secondary"
            size="sm"
            className="mt-6"
            disabled={products.isFetchingNextPage}
            onClick={() => void products.fetchNextPage()}
          >
            {products.isFetchingNextPage ? "Lädt …" : "Weitere laden"}
          </Button>
        ) : null}
      </div>
    </section>
  );
}

function ProductRow({ item, stock, onEbay }: { item: ProductListItemOut; stock: ProductStockOut | undefined; onEbay: boolean }) {
  const picture = readyPicture(item.main_image);
  const free = stock?.free ?? 0;
  const reserved = stock?.reserved ?? 0;
  return (
    <li>
      <Link
        href={`/admin/modelle/${item.id}` as Route}
        className="grid grid-cols-[4rem_minmax(0,1fr)] items-center gap-4 py-3 hover:bg-stage sm:grid-cols-[4rem_minmax(0,1fr)_auto]"
      >
        <span className="relative block size-16 overflow-hidden rounded-sm bg-stage">
          {picture ? (
            <ResponsivePicture image={picture} alt="" sizes="64px" variant="thumb" fit="cover" />
          ) : (
            <span className="absolute inset-0 flex items-center justify-center text-center text-[0.625rem] leading-tight text-ink-tertiary">
              {item.main_image ? "…" : "ohne Foto"}
            </span>
          )}
        </span>
        <span className="min-w-0">
          <span className="block truncate font-medium">{item.name}</span>
          <span className="mt-1 flex flex-wrap items-center gap-2">
            <StatusBadge tone={STATUS_TONES[item.status]}>{PRODUCT_STATUS_LABELS[item.status]}</StatusBadge>
            {onEbay ? <StatusBadge tone="accent">eBay</StatusBadge> : null}
            <span className="font-mono text-hint text-ink-tertiary">{formatProductNumber(item.number)}</span>
            {item.price_from_cents !== null ? (
              <span className="text-hint text-ink-tertiary tabular-nums">ab {formatPrice(item.price_from_cents)}</span>
            ) : null}
          </span>
          {stock && stock.places.length > 0 ? (
            <span className="mt-1 block truncate text-hint text-ink-secondary">{placesLine(stock.places)}</span>
          ) : null}
        </span>
        <span className="col-span-2 text-small tabular-nums sm:col-span-1 sm:text-right">
          <span className={free === 0 ? "text-ink-tertiary" : "font-medium"}>{free} frei</span>
          {reserved > 0 ? <span className="text-ink-secondary"> · {reserved} reserviert</span> : null}
          {stock && stock.labeled > 0 ? <span className="block text-hint text-warning">{stock.labeled} unverbucht</span> : null}
        </span>
      </Link>
    </li>
  );
}

/** Among the drafts: every one that lacks nothing goes into the shop at once. */
function PublishReady() {
  const queryClient = useQueryClient();
  const publish = useMutation<PublishedOut, ApiProblem>({
    mutationFn: () => publishReadyProducts(),
    onSuccess() {
      void queryClient.invalidateQueries({ queryKey: ADMIN_PRODUCTS_KEY });
    },
  });
  const published = publish.data?.published ?? [];
  return (
    <div className="mt-4 flex flex-wrap items-center gap-3 text-small">
      <Button type="button" size="sm" variant="secondary" disabled={publish.isPending} onClick={() => publish.mutate()}>
        {publish.isPending ? "Veröffentlicht …" : "Fertige Entwürfe in den Shop"}
      </Button>
      <span role="status" className="text-ink-secondary">
        {publish.isError ? errorMessage(publish.error) : null}
        {publish.isSuccess
          ? published.length === 0
            ? "Kein Entwurf ist schon fertig; auf der Seite des Modells steht, was fehlt."
            : `${published.length === 1 ? "1 Modell ist" : `${published.length} Modelle sind`} jetzt im Shop.`
          : null}
      </span>
    </div>
  );
}
