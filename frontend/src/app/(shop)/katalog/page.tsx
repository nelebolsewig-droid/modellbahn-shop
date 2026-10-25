import type { Metadata, Route } from "next";
import Link from "next/link";
import { permanentRedirect } from "next/navigation";

import { CATALOG_SORTS, sortFor } from "@/components/shop/catalog-nav";
import { EmptyState } from "@/components/shop/scale-catalog";
import { ScaleGates } from "@/components/shop/scale-gates";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ProductCard } from "@/components/ui/product-card";
import type { NavigationOut, StoreProductPageOut } from "@/lib/api/generated/model";
import { fetchStore } from "@/lib/api/server";
import { busiestScale, catalogPath, findScale } from "@/lib/catalog/scales";
import { loadNavigation } from "@/lib/catalog/store-data";
import { firstParam } from "@/lib/search-params";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
  title: "Katalog",
  description: "3D-gedruckte Modelle von Z bis G und für Straßenfahrzeuge: erst den Maßstab wählen, dann die Kategorie.",
};

const PAGE_SIZE = "24";

type SearchParams = Record<string, string | string[] | undefined>;

/**
 * Addresses from before the shop was sorted by scale (/katalog?spur=H0&kategorie=lkw)
 * lead to the same list under its new address; without a scale, to the scale with the
 * most models in that category.
 */
function legacyTarget(navigation: NavigationOut, params: SearchParams): Route | null {
  const spur = firstParam(params.spur);
  const kategorie = firstParam(params.kategorie);
  if (!spur && !kategorie) {
    return null;
  }
  const category = navigation.categories.find((candidate) => candidate.slug === kategorie);
  const scale =
    (spur ? findScale(navigation.scales, spur) : undefined) ??
    (category ? busiestScale(navigation.scales, navigation.categories, category.id) : undefined);
  if (scale === undefined) {
    return null;
  }
  return catalogPath({
    scale: scale.code,
    category: category?.slug,
    epoche: firstParam(params.epoche) || undefined,
    suche: firstParam(params.suche)?.trim() || undefined,
    sortierung: firstParam(params.sortierung) || undefined,
  });
}

export default async function CatalogPage({ searchParams }: PageProps<"/katalog">) {
  const params = await searchParams;
  const navigation = await loadNavigation();
  const target = navigation ? legacyTarget(navigation, params) : null;
  if (target) {
    permanentRedirect(target);
  }
  const suche = firstParam(params.suche)?.trim() || undefined;

  return (
    <div className="mx-auto max-w-6xl px-5 py-14 sm:px-8 lg:py-20">
      <header className="grid items-end gap-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div>
          <p className="label-caps text-ink-tertiary">Katalog</p>
          <h1 className="mt-4 text-title sm:text-display">{suche ? `Suche: „${suche}“` : "Welcher Maßstab?"}</h1>
          <p className="mt-5 max-w-xl text-body-lg text-ink-secondary">
            {suche
              ? "Treffer aus allen Maßstäben. Für ein Modell in deinem Maßstab wähle ihn unten."
              : "Erst den Maßstab, dann die Kategorie: Gebäude, Schienen- und Straßenfahrzeuge aus unserer Werkstatt, jeweils maßstäblich konstruiert."}
          </p>
        </div>
        <form action="/katalog" role="search" className="space-y-3">
          <label htmlFor="suche" className="label-caps text-ink-tertiary">
            In allen Maßstäben suchen
          </label>
          <div className="flex gap-2">
            <Input id="suche" name="suche" type="search" defaultValue={suche} placeholder="z. B. Stellwerk" />
            <Button type="submit" variant="secondary" className="shrink-0">
              Suchen
            </Button>
          </div>
        </form>
      </header>

      <div className="mt-14">
        {suche ? (
          <SearchResults navigation={navigation} suche={suche} params={params} />
        ) : navigation ? (
          <ScaleGates scales={navigation.scales} />
        ) : (
          <EmptyState title="Der Katalog ist gerade nicht erreichbar">
            <p>Bitte versuche es gleich noch einmal.</p>
          </EmptyState>
        )}
      </div>
    </div>
  );
}

async function SearchResults({
  navigation,
  suche,
  params,
}: {
  navigation: NavigationOut | null;
  suche: string;
  params: SearchParams;
}) {
  const sortierung = firstParam(params.sortierung) || undefined;
  const page = await fetchStore<StoreProductPageOut>("/products", {
    q: suche,
    sort: sortFor(sortierung),
    cursor: firstParam(params.weiter) || undefined,
    limit: PAGE_SIZE,
  });
  const items = page?.items ?? [];
  const names = new Map((navigation?.scales ?? []).map((scale) => [scale.code, scale.name]));
  const href = (extra: Record<string, string | undefined>) => {
    const query = new URLSearchParams({ suche });
    for (const [name, value] of Object.entries(extra)) {
      if (value) {
        query.set(name, value);
      }
    }
    return `/katalog?${query.toString()}` as Route;
  };

  if (items.length === 0) {
    return (
      <EmptyState title="Nichts gefunden">
        <p>Zu „{suche}“ gibt es noch kein Modell.</p>
        <Link href="/katalog" className="mt-4 inline-block text-accent underline-offset-4 hover:underline">
          Zu den Maßstäben
        </Link>
      </EmptyState>
    );
  }
  return (
    <section aria-label="Suchergebnisse">
      <nav aria-label="Sortierung" className="mb-8 flex flex-wrap items-baseline justify-end gap-x-5 gap-y-2 text-small">
        <span className="label-caps text-ink-tertiary" aria-hidden="true">
          Sortieren
        </span>
        {CATALOG_SORTS.map((entry) => {
          const current = entry.sort === sortFor(sortierung);
          return (
            <Link
              key={entry.sort}
              href={href({ sortierung: entry.param })}
              aria-current={current ? "page" : undefined}
              className={cn(
                "border-b py-1 transition-colors",
                current ? "border-selected font-medium text-ink" : "border-transparent text-ink-secondary hover:text-ink",
              )}
            >
              {entry.label}
            </Link>
          );
        })}
      </nav>
      <ul className="grid gap-x-8 gap-y-12 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((item, index) => (
          <li key={item.slug}>
            <ProductCard
              href={`/produkte/${item.slug}` as Route}
              name={item.name}
              summary={item.summary}
              scales={item.scale_codes.map((code) => names.get(code) ?? code)}
              priceFromCents={item.price_from_cents}
              image={item.image}
              priority={index < 3}
            />
          </li>
        ))}
      </ul>
      {page?.next_cursor ? (
        <div className="mt-14 flex justify-center">
          <Button asChild variant="secondary">
            <Link href={href({ sortierung, weiter: page.next_cursor })}>Weitere Treffer</Link>
          </Button>
        </div>
      ) : null}
    </section>
  );
}
