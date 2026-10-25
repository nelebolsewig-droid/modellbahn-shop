import type { Route } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { CatalogSort, CategoryTree, EpochFilter, ScaleSwitch, categoryTrail, sortFor } from "@/components/shop/catalog-nav";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ProductCard } from "@/components/ui/product-card";
import { ScaleRule } from "@/components/ui/scale-rule";
import type { NavigationOut, StoreProductPageOut } from "@/lib/api/generated/model";
import { fetchStore } from "@/lib/api/server";
import { catalogPath, findScale, millimetresPerMetre, scaleLabel, scaleSlug, type CatalogLocation } from "@/lib/catalog/scales";
import { loadNavigation } from "@/lib/catalog/store-data";
import { firstParam } from "@/lib/search-params";

const PAGE_SIZE = "24";

type SearchParams = Record<string, string | string[] | undefined>;

/** Scale and category an address names, or null if either does not exist. */
export function resolveLocation(
  navigation: NavigationOut,
  scaleSlugParam: string,
  categorySlug: string | undefined,
  params: SearchParams = {},
) {
  const scale = findScale(navigation.scales, decodeURIComponent(scaleSlugParam));
  const category = categorySlug
    ? navigation.categories.find((candidate) => candidate.slug === decodeURIComponent(categorySlug))
    : undefined;
  if (scale === undefined || (categorySlug !== undefined && category === undefined)) {
    return null;
  }
  const location: CatalogLocation = {
    scale: scale.code,
    category: category?.slug,
    epoche: firstParam(params.epoche) || undefined,
    suche: firstParam(params.suche)?.trim() || undefined,
    sortierung: firstParam(params.sortierung) || undefined,
  };
  return { scale, category, location };
}

type ScaleCatalogProps = {
  scaleSlug: string;
  categorySlug?: string;
  searchParams: SearchParams;
};

/**
 * The models of one scale, narrowed by category, epoch and search: the shop's list
 * below /katalog/{maßstab}. Categories without models in this scale are not offered.
 */
export async function ScaleCatalog({ scaleSlug: scaleParam, categorySlug, searchParams }: ScaleCatalogProps) {
  const navigation = await loadNavigation();
  const resolved = navigation === null ? null : resolveLocation(navigation, scaleParam, categorySlug, searchParams);
  if (navigation === null || resolved === null) {
    notFound();
  }
  const { scale, category, location } = resolved;
  const page = await fetchStore<StoreProductPageOut>("/products", {
    scale: scale.code,
    category: category?.slug,
    epoch: location.epoche,
    q: location.suche,
    sort: sortFor(location.sortierung),
    cursor: firstParam(searchParams.weiter) || undefined,
    limit: PAGE_SIZE,
  });
  const items = page?.items ?? [];
  const trail = categoryTrail(navigation.categories, category?.slug);
  const scaleNames = new Map(navigation.scales.map((s) => [s.code, s.name]));
  const filtered = Boolean(location.suche || location.epoche || location.category);

  return (
    <div className="mx-auto max-w-6xl px-5 py-12 sm:px-8 lg:py-16">
      <nav aria-label="Brotkrumen">
        <ol className="flex flex-wrap items-center gap-2 text-hint text-ink-tertiary">
          <li>
            <Link href="/katalog" className="hover:text-ink">
              Katalog
            </Link>
          </li>
          <li className="flex items-center gap-2">
            <span aria-hidden="true">/</span>
            <Link href={catalogPath({ scale: scale.code })} className="hover:text-ink">
              {scaleLabel(scale)}
            </Link>
          </li>
          {trail.map((step) => (
            <li key={step.id} className="flex items-center gap-2">
              <span aria-hidden="true">/</span>
              <Link href={catalogPath({ scale: scale.code, category: step.slug })} className="hover:text-ink">
                {step.name}
              </Link>
            </li>
          ))}
        </ol>
      </nav>

      <header className="mt-8 grid items-end gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,20rem)]">
        <div>
          <p className="label-caps text-ink-tertiary">Maßstab {scaleLabel(scale)}</p>
          <h1 className="mt-4 text-title sm:text-display">{category ? category.name : `Alle Modelle in ${scale.name}`}</h1>
        </div>
        {/* Against the largest scale of the shop, so the tape shows how big this one is. */}
        <ScaleRule
          ratioDenominator={scale.ratio_denominator}
          longestMillimetres={Math.max(...navigation.scales.map((s) => millimetresPerMetre(s.ratio_denominator)))}
        />
      </header>
      <div className="mt-8">
        <ScaleSwitch location={location} scales={navigation.scales} categories={navigation.categories} />
      </div>

      <div className="mt-12 grid gap-10 lg:grid-cols-[16rem_minmax(0,1fr)] lg:gap-14">
        <aside className="space-y-10">
          <form action={catalogPath({ scale: scale.code, category: category?.slug })} role="search" className="space-y-3">
            <label htmlFor="suche" className="label-caps text-ink-tertiary">
              Suche in {scale.name}
            </label>
            {location.epoche ? <input type="hidden" name="epoche" value={location.epoche} /> : null}
            {location.sortierung ? <input type="hidden" name="sortierung" value={location.sortierung} /> : null}
            <Input id="suche" name="suche" type="search" defaultValue={location.suche} placeholder="z. B. Feuerwehr" />
            <Button type="submit" variant="secondary" size="sm">
              Suchen
            </Button>
          </form>
          <CategoryTree location={location} categories={navigation.categories} />
          <EpochFilter location={location} epochs={navigation.epochs} />
        </aside>

        <section aria-label="Modelle">
          {items.length > 0 ? <CatalogSort location={location} className="mb-8 justify-end" /> : null}
          {items.length === 0 ? (
            <EmptyState title={filtered ? "Nichts gefunden" : "Bald im Katalog"}>
              <p>
                {filtered
                  ? `Zu dieser Auswahl gibt es in ${scale.name} noch kein Modell.`
                  : `Die ersten Modelle in ${scale.name} werden gerade fotografiert.`}
              </p>
              {filtered ? (
                <Link href={catalogPath({ scale: scale.code })} className="mt-4 inline-block text-accent underline-offset-4 hover:underline">
                  Alle Modelle in {scale.name}
                </Link>
              ) : null}
            </EmptyState>
          ) : (
            <>
              <ul className="grid gap-x-8 gap-y-12 sm:grid-cols-2 xl:grid-cols-3">
                {items.map((item, index) => (
                  <li key={item.slug}>
                    <ProductCard
                      href={`/produkte/${item.slug}?massstab=${scaleSlug(scale.code)}` as Route}
                      name={item.name}
                      summary={item.summary}
                      scales={item.scale_codes.map((code) => scaleNames.get(code) ?? code)}
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
                    <Link href={catalogPath({ ...location, weiter: page.next_cursor })}>Weitere Modelle</Link>
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

export function EmptyState({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-lg bg-stage px-8 py-16 text-center">
      <p className="label-caps text-ink-tertiary">Gleis leer</p>
      <p className="mt-4 text-heading">{title}</p>
      <div className="mx-auto mt-3 max-w-md text-ink-secondary">{children}</div>
    </div>
  );
}
