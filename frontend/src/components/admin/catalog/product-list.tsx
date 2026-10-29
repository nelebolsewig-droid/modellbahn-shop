"use client";

import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type { Route } from "next";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Panel } from "@/components/admin/panel";
import { FormError } from "@/components/forms/form-error";
import { SubmitButton } from "@/components/forms/submit-button";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { OptionGroup, OptionPill } from "@/components/ui/option-pill";
import { PendingNotice } from "@/components/ui/pending-notice";
import { ResponsivePicture } from "@/components/ui/responsive-picture";
import { StatusBadge } from "@/components/ui/status-badge";
import { createProduct, listProducts, publishReadyProducts } from "@/lib/api/generated/admin-catalog/admin-catalog";
import type {
  ProductListItemOut,
  ProductOut,
  ProductPageOut,
  ProductStatus,
  PublishedOut,
} from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";
import { formatPrice, formatProductNumber } from "@/lib/catalog/format";
import { readyPicture } from "@/lib/catalog/images";
import { PRODUCT_STATUS_LABELS } from "@/lib/catalog/labels";
import { formatEventTime } from "@/lib/format";
import { errorMessage, fieldErrorMessage } from "@/lib/i18n/problems";

import { ADMIN_PRODUCTS_KEY, productQueryKey } from "./use-product";

const PAGE_SIZE = 25;

type StatusFilter = ProductStatus | "all";

const FILTERS: readonly { value: StatusFilter; label: string }[] = [
  { value: "all", label: "Alle" },
  { value: "draft", label: "Entwürfe" },
  { value: "active", label: "Im Shop" },
  { value: "archived", label: "Archiviert" },
];

export const STATUS_TONES = {
  draft: "neutral",
  active: "success",
  archived: "warning",
} as const satisfies Record<ProductStatus, "neutral" | "success" | "warning">;

/** The catalogue of the Stellwerk: every product, newest first, with a quick way to add one. */
export function ProductList() {
  const [status, setStatus] = useState<StatusFilter>("all");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const products = useInfiniteQuery<ProductPageOut, ApiProblem>({
    queryKey: [...ADMIN_PRODUCTS_KEY, { status, query }],
    queryFn: ({ pageParam, signal }) =>
      listProducts(
        {
          limit: PAGE_SIZE,
          ...(status !== "all" && { status }),
          ...(query && { q: query }),
          ...(typeof pageParam === "string" && { cursor: pageParam }),
        },
        { signal },
      ),
    initialPageParam: null,
    getNextPageParam: (page) => page.next_cursor,
  });
  const items = products.data?.pages.flatMap((page) => page.items) ?? [];

  function onSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setQuery(search.trim());
  }

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <Panel title="Produkte" code="KAT 01">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <OptionGroup
            label="Zustand"
            value={status}
            onValueChange={(value) => setStatus(value as StatusFilter)}
          >
            {FILTERS.map((filter) => (
              <OptionPill key={filter.value} value={filter.value} tone="accent">
                {filter.label}
              </OptionPill>
            ))}
          </OptionGroup>
          <form role="search" onSubmit={onSearch} className="flex items-end gap-2">
            <FormField label="Suche" className="w-56">
              {(control) => (
                <Input
                  {...control}
                  type="search"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Name, Beschreibung …"
                />
              )}
            </FormField>
            <Button type="submit" variant="secondary" size="sm" className="mb-0.5">
              Suchen
            </Button>
          </form>
        </div>

        <div className="mt-6">
          {products.isPending ? (
            <PendingNotice>Produkte werden geladen …</PendingNotice>
          ) : products.isError ? (
            <p role="alert" className="text-small text-danger">
              {errorMessage(products.error)}
            </p>
          ) : items.length === 0 ? (
            <p className="rounded-md border border-dashed border-line-strong px-5 py-10 text-center text-small text-ink-secondary">
              {query || status !== "all"
                ? "Keine Produkte für diese Auswahl."
                : "Noch kein Produkt angelegt. Rechts geht es los."}
            </p>
          ) : (
            <ul className="divide-y divide-line">
              {items.map((item) => (
                <ProductRow key={item.id} item={item} />
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
      </Panel>
      <div className="space-y-6">
        <NewProductForm />
        <DraftsPanel />
      </div>
    </div>
  );
}

function ProductRow({ item }: { item: ProductListItemOut }) {
  const picture = readyPicture(item.main_image);
  return (
    <li>
      <Link
        href={`/admin/katalog/${item.id}` as Route}
        className="grid grid-cols-[3.5rem_minmax(0,1fr)_auto] items-center gap-4 rounded-sm py-3 hover:bg-stage"
      >
        <span className="relative block size-14 overflow-hidden rounded-sm bg-stage">
          {picture ? (
            <ResponsivePicture image={picture} alt="" sizes="56px" variant="thumb" fit="cover" />
          ) : (
            <span className="absolute inset-0 flex items-center justify-center font-mono text-[0.625rem] text-ink-tertiary">
              {item.main_image ? "…" : "—"}
            </span>
          )}
        </span>
        <span className="min-w-0">
          <span className="block truncate font-medium">{item.name}</span>
          <span className="mt-0.5 flex flex-wrap gap-x-3 font-mono text-hint text-ink-tertiary">
            <span>{formatProductNumber(item.number)}</span>
            {item.scale_codes.length > 0 ? <span>{item.scale_codes.join(" · ")}</span> : null}
            <span>{item.variant_count === 1 ? "1 Variante" : `${item.variant_count} Varianten`}</span>
          </span>
        </span>
        <span className="flex flex-col items-end gap-1 text-right">
          <StatusBadge tone={STATUS_TONES[item.status]}>{PRODUCT_STATUS_LABELS[item.status]}</StatusBadge>
          <span className="text-hint text-ink-tertiary tabular-nums">
            {item.price_from_cents !== null ? `ab ${formatPrice(item.price_from_cents)} · ` : ""}
            {formatEventTime(new Date(item.updated_at))}
          </span>
        </span>
      </Link>
    </li>
  );
}

function NewProductForm() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const create = useMutation<ProductOut, ApiProblem, string>({
    mutationFn: (productName) => createProduct({ name: productName }),
    onSuccess(product) {
      queryClient.setQueryData(productQueryKey(product.id), product);
      void queryClient.invalidateQueries({ queryKey: ADMIN_PRODUCTS_KEY });
      router.push(`/admin/katalog/${product.id}` as Route);
    },
  });
  const fieldError = create.error?.fieldErrors.find((error) => error.field === "name");

  return (
    <Panel title="Neues Produkt" code="KAT 02">
      <form
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          if (name.trim()) {
            create.mutate(name.trim());
          }
        }}
      >
        <FormError message={create.isError && !fieldError ? errorMessage(create.error) : undefined} />
        <FormField
          label="Name"
          hint="Die Adresse im Shop entsteht daraus; alles Weitere folgt im Editor."
          error={fieldError ? fieldErrorMessage("name", fieldError.code) : undefined}
        >
          {(control) => (
            <Input
              {...control}
              value={name}
              maxLength={120}
              onChange={(event) => setName(event.target.value)}
              placeholder="z. B. Stellwerk Altenau"
            />
          )}
        </FormField>
        <SubmitButton pending={create.isPending} pendingLabel="Legt an …" className="mt-5" disabled={!name.trim()}>
          Entwurf anlegen
        </SubmitButton>
      </form>
    </Panel>
  );
}

/** The end of a day at the crates: every draft that lacks nothing goes into the shop at once. */
function DraftsPanel() {
  const queryClient = useQueryClient();
  const publish = useMutation<PublishedOut, ApiProblem>({
    mutationFn: () => publishReadyProducts(),
    onSuccess() {
      void queryClient.invalidateQueries({ queryKey: ADMIN_PRODUCTS_KEY });
    },
  });
  const published = publish.data?.published ?? [];

  return (
    <Panel title="Entwürfe" code="KAT 03">
      <p className="text-small text-ink-secondary">
        Modelle aus der Kiste erfasst? Entwürfe mit Kategorie, aktiver Variante und fertigem Hauptbild gehen hier in einem
        Schritt in den Shop; die anderen bleiben, bis sie vollständig sind.
      </p>
      <div className="mt-5 flex flex-wrap gap-2">
        <Button asChild variant="secondary" size="sm">
          <Link href="/admin/erfassen">Schnellerfassung</Link>
        </Button>
        <Button
          type="button"
          size="sm"
          disabled={publish.isPending}
          aria-busy={publish.isPending || undefined}
          onClick={() => {
            if (window.confirm("Alle fertigen Entwürfe jetzt im Shop zeigen?")) {
              publish.mutate();
            }
          }}
        >
          {publish.isPending ? "Veröffentlicht …" : "Fertige veröffentlichen"}
        </Button>
      </div>
      <div role="status" className="mt-4 text-small empty:hidden">
        {publish.isError ? <p className="text-danger">{errorMessage(publish.error)}</p> : null}
        {publish.isSuccess ? (
          published.length === 0 ? (
            <p className="text-ink-secondary">Kein Entwurf ist schon fertig. Im Editor steht, was jeweils fehlt.</p>
          ) : (
            <>
              <p className="font-medium text-success">
                {published.length === 1 ? "1 Produkt ist jetzt im Shop:" : `${published.length} Produkte sind jetzt im Shop:`}
              </p>
              <ul className="mt-2 space-y-1">
                {published.map((item) => (
                  <li key={item.id}>
                    <Link href={`/admin/katalog/${item.id}` as Route} className="text-accent hover:underline">
                      {item.name}
                    </Link>
                  </li>
                ))}
              </ul>
            </>
          )
        ) : null}
      </div>
    </Panel>
  );
}
