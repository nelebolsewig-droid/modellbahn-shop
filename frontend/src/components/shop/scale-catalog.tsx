import type { Route } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import {
  CatalogSort,
  CategoryTree,
  EpochFilter,
  FinishSwitch,
  LabelFilter,
  ScaleSwitch,
  categoryTrail,
  sortFor,
} from "@/components/shop/catalog-nav";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ProductCard } from "@/components/ui/product-card";
import { ScaleRule } from "@/components/ui/scale-rule";
import type { NavigationOut, StoreProductPageOut } from "@/lib/api/generated/model";
import { fetchStore } from "@/lib/api/server";
import { FINISH_FILTERS, finishFor, labelFor, labelName } from "@/lib/catalog/filters";
import { catalogPath, findScale, millimetresPerMetre, scaleLabel, scaleSlug, type CatalogLocation } from "@/lib/catalog/scales";
import { RememberScale } from "@/lib/catalog/last-scale";
import { loadNavigation } from "@/lib/catalog/store-data";
import { firstParam } from "@/lib/search-params";
import { finishName } from "@/components/ui/photo-mark";

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
    ausfuehrung: finishFor(firstParam(params.ausfuehrung)) ? firstParam(params.ausfuehrung) : undefined,
    label: labelFor(firstParam(params.label)),
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
    finish: finishFor(location.ausfuehrung),
    label: location.label,
    q: location.suche,
    sort: sortFor(location.sortierung),
    cursor: firstParam(searchParams.weiter) || undefined,
    limit: PAGE_SIZE,
  });
  const items = page?.items ?? [];
  const trail = categoryTrail(navigation.categories, category?.slug);
  const scaleNames = new Map(navigation.scales.map((s) => [s.code, s.name]));
  const filtered = Boolean(
    location.suche || location.epoche || location.category || location.ausfuehrung || location.label,
  );

  return (
    <div className="mx-auto max-w-6xl px-5 py-12 sm:px-8 lg:py-16">
      <RememberScale code={scale.code} name={scale.name} />
      <nav aria-label="Brotkrumen">
        <ol className="flex flex-wrap items-center gap-2 text-hint text-ink-tertiary">
          <li>
            <Link href="/katalog" className="hover:text-ink">
              Modelle
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
          <h1 className="mt-4 text-title hyphens-auto break-words sm:text-display">{category ? category.name : `Alle Modelle in ${scale.name}`}</h1>
        </div>
        {/* Against the largest scale of the shop, so the tape shows how big this one is. */}
        <ScaleRule
          ratioDenominator={scale.ratio_denominator}
          longestMillimetres={Math.max(...navigation.scales.map((s) => millimetresPerMetre(s.ratio_denominator)))}
        />
      </header>
      <div className="mt-8 flex flex-wrap items-center gap-x-8 gap-y-3">
        <ScaleSwitch location={location} scales={navigation.scales} categories={navigation.categories} />
        <FinishSwitch location={location} />
      </div>

      <div className="mt-10 grid gap-10 lg:mt-12 lg:grid-cols-[16rem_minmax(0,1fr)] lg:gap-14">
        {/* Phones: the filters fold away, so the models come right after the heading. */}
        <details className="group rounded-lg border border-line bg-surface lg:hidden">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-5 py-4 [&::-webkit-details-marker]:hidden">
            <span>
              <span className="block label-caps text-ink-tertiary">Filter</span>
              <span className="mt-1 block text-small font-medium">
                {[
                  category?.name ?? "Alle Kategorien",
                  FINISH_FILTERS.find((entry) => entry.param === location.ausfuehrung)?.label,
                  location.label && labelName(location.label),
                  location.epoche && `Epoche ${location.epoche}`,
                  location.suche && `„${location.suche}“`,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
            </span>
            <span aria-hidden="true" className="text-ink-tertiary transition-transform duration-150 group-open:rotate-180">
              ▾
            </span>
          </summary>
          <div className="space-y-10 border-t border-line px-5 py-6">
            <Filters navigation={navigation} location={location} scaleName={scale.name} inputId="suche-mobil" />
          </div>
        </details>
        <aside className="hidden space-y-10 lg:block">
          <Filters navigation={navigation} location={location} scaleName={scale.name} inputId="suche" />
        </aside>

        <section aria-label="Modelle">
          {items.length > 0 ? <CatalogSort location={location} className="mb-8 lg:justify-end" /> : null}
          {items.length === 0 ? (
            <EmptyState title={filtered ? "Nichts gefunden" : "Kommt bald"}>
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
                      finishes={item.finish_codes.map(finishName)}
                      label={item.label}
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

type FiltersProps = {
  navigation: NavigationOut;
  location: CatalogLocation;
  scaleName: string;
  /** The page shows the filters twice (folded on phones), each with its own field id. */
  inputId: string;
};

/** Search within the scale, kit or finished model, label, the category tree and the epochs. */
function Filters({ navigation, location, scaleName, inputId }: FiltersProps) {
  return (
    <>
      <form action={catalogPath({ scale: location.scale, category: location.category })} role="search" className="space-y-3">
        <label htmlFor={inputId} className="label-caps text-ink-tertiary">
          Suche in {scaleName}
        </label>
        {location.ausfuehrung ? <input type="hidden" name="ausfuehrung" value={location.ausfuehrung} /> : null}
        {location.label ? <input type="hidden" name="label" value={location.label} /> : null}
        {location.epoche ? <input type="hidden" name="epoche" value={location.epoche} /> : null}
        {location.sortierung ? <input type="hidden" name="sortierung" value={location.sortierung} /> : null}
        <Input id={inputId} name="suche" type="search" defaultValue={location.suche} placeholder="z. B. Feuerwehr" />
        <Button type="submit" variant="secondary" size="sm">
          Suchen
        </Button>
      </form>
      <LabelFilter location={location} />
      <CategoryTree location={location} categories={navigation.categories} />
      <EpochFilter location={location} epochs={navigation.epochs} />
    </>
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
