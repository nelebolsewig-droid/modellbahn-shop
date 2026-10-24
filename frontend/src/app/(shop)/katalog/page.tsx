import type { Metadata, Route } from "next";
import Link from "next/link";
import { connection } from "next/server";
import type { ReactNode } from "react";

import { CatalogFilters, catalogHref, type CatalogQuery } from "@/components/shop/catalog-filters";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ProductCard } from "@/components/ui/product-card";
import type { NavigationOut, StoreProductPageOut } from "@/lib/api/generated/model";
import { fetchStore } from "@/lib/api/server";
import { firstParam } from "@/lib/search-params";

export const metadata: Metadata = {
  title: "Katalog",
  description: "3D-gedruckte Modellbahn-Artikel in H0, TT und N: Gebäude, Bausätze und Kleinteile.",
};

const PAGE_SIZE = "24";

export default async function CatalogPage({ searchParams }: PageProps<"/katalog">) {
  // Rendered per request: the catalogue changes whenever something is published.
  await connection();
  const params = await searchParams;
  const query: CatalogQuery = {
    spur: firstParam(params.spur) || undefined,
    kategorie: firstParam(params.kategorie) || undefined,
    suche: firstParam(params.suche)?.trim() || undefined,
  };
  const cursor = firstParam(params.weiter) || undefined;
  const [navigation, page] = await Promise.all([
    fetchStore<NavigationOut>("/navigation"),
    fetchStore<StoreProductPageOut>("/products", {
      scale: query.spur,
      category: query.kategorie,
      q: query.suche,
      cursor,
      limit: PAGE_SIZE,
    }),
  ]);
  const category = navigation?.categories.find((c) => c.slug === query.kategorie);
  const items = page?.items ?? [];

  return (
    <div className="mx-auto max-w-6xl px-5 py-14 sm:px-8 lg:py-20">
      <header>
        <p className="label-caps text-ink-tertiary">Katalog</p>
        <h1 className="mt-4 text-title sm:text-display">{category ? category.name : "Alle Modelle"}</h1>
        <p className="mt-5 max-w-xl text-body-lg text-ink-secondary">
          Gebäude, Bausätze und Kleinteile aus unserer Werkstatt, jede Spurweite maßstäblich
          konstruiert.
        </p>
      </header>

      <div className="mt-12 grid gap-10 lg:grid-cols-[16rem_minmax(0,1fr)] lg:gap-14">
        <aside className="space-y-8">
          <form action="/katalog" role="search" className="space-y-3">
            <label htmlFor="suche" className="label-caps text-ink-tertiary">
              Suche
            </label>
            {query.spur ? <input type="hidden" name="spur" value={query.spur} /> : null}
            {query.kategorie ? <input type="hidden" name="kategorie" value={query.kategorie} /> : null}
            <Input id="suche" name="suche" type="search" defaultValue={query.suche} placeholder="z. B. Stellwerk" />
            <Button type="submit" variant="secondary" size="sm">
              Suchen
            </Button>
          </form>
          {navigation ? (
            <CatalogFilters query={query} scales={navigation.scales} categories={navigation.categories} />
          ) : null}
        </aside>

        <section aria-label="Modelle">
          {page === null ? (
            <EmptyState title="Diese Kategorie gibt es nicht">
              <Link href="/katalog" className="text-accent underline-offset-4 hover:underline">
                Alle Modelle ansehen
              </Link>
            </EmptyState>
          ) : items.length === 0 ? (
            <EmptyState title={query.suche || query.spur || query.kategorie ? "Nichts gefunden" : "Bald im Katalog"}>
              <p>
                {query.suche || query.spur || query.kategorie
                  ? "Zu dieser Auswahl gibt es noch kein Modell."
                  : "Die ersten Modelle werden gerade fotografiert."}
              </p>
            </EmptyState>
          ) : (
            <>
              <ul className="grid gap-x-8 gap-y-12 sm:grid-cols-2 xl:grid-cols-3">
                {items.map((item, index) => (
                  <li key={item.slug}>
                    <ProductCard
                      href={`/produkte/${item.slug}` as Route}
                      name={item.name}
                      summary={item.summary}
                      scales={item.scale_codes}
                      priceFromCents={item.price_from_cents}
                      image={item.image}
                      priority={index < 3}
                    />
                  </li>
                ))}
              </ul>
              {page.next_cursor ? (
                <div className="mt-14 flex justify-center">
                  <Button asChild variant="secondary">
                    <Link href={catalogHref({ ...query, weiter: page.next_cursor })}>
                      Weitere Modelle
                    </Link>
                  </Button>
                </div>
              ) : null}
            </>
          )}
        </section>
      </div>
    </div>
  );
}

function EmptyState({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-lg bg-stage px-8 py-16 text-center">
      <p className="label-caps text-ink-tertiary">Gleis leer</p>
      <p className="mt-4 text-heading">{title}</p>
      <div className="mx-auto mt-3 max-w-md text-ink-secondary">{children}</div>
    </div>
  );
}
