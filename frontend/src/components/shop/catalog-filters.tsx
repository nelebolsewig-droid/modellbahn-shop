import Link from "next/link";
import type { Route } from "next";

import type { CategoryOut, EpochOut, ListStoreProductsSort, ScaleOut } from "@/lib/api/generated/model";
import { cn } from "@/lib/utils";

export type CatalogQuery = {
  spur?: string;
  kategorie?: string;
  epoche?: string;
  suche?: string;
  sortierung?: string;
};

/** The orders of the list, by their German address; the first is the default and not in the URL. */
export const CATALOG_SORTS = [
  { param: undefined, sort: "newest", label: "Neueste" },
  { param: "preis-auf", sort: "price_asc", label: "Preis aufsteigend" },
  { param: "preis-ab", sort: "price_desc", label: "Preis absteigend" },
  { param: "name", sort: "name", label: "Name" },
] as const satisfies readonly { param: string | undefined; sort: ListStoreProductsSort; label: string }[];

/** The API's order for the `sortierung` parameter; unknown values fall back to the newest first. */
export function sortFor(param: string | undefined): ListStoreProductsSort {
  return CATALOG_SORTS.find((entry) => entry.param === param)?.sort ?? "newest";
}

const PARAM_ORDER = ["spur", "kategorie", "epoche", "suche", "sortierung", "weiter"] as const;

/**
 * The catalogue's address for a combination of filters (empty ones are left out);
 * `weiter` is the cursor of the next page.
 */
export function catalogHref(query: CatalogQuery & { weiter?: string }): Route {
  const params = new URLSearchParams();
  // A fixed order: the same list always has the same address.
  for (const name of PARAM_ORDER) {
    const value = query[name];
    if (value) {
      params.set(name, value);
    }
  }
  const search = params.toString();
  return (search ? `/katalog?${search}` : "/katalog") as Route;
}

type FilterLinkProps = {
  href: Route;
  /** Drawn as chosen: the current filter, or the parent of the chosen subcategory. */
  active: boolean;
  /** Only the link to the list on screen is the current page; defaults to `active`. */
  current?: boolean;
  children: string;
  "aria-label"?: string;
  title?: string;
};

function FilterLink({ href, active, current = active, children, "aria-label": label, title }: FilterLinkProps) {
  return (
    <Link
      href={href}
      aria-current={current ? "page" : undefined}
      aria-label={label}
      title={title}
      className={cn(
        "inline-flex h-10 items-center rounded-full border px-4 text-sm font-medium transition-colors duration-150",
        active
          ? "border-selected bg-selected text-on-selected"
          : "border-line-strong bg-surface text-ink hover:border-ink",
      )}
    >
      {children}
    </Link>
  );
}

type CatalogFiltersProps = {
  query: CatalogQuery;
  scales: readonly ScaleOut[];
  categories: readonly CategoryOut[];
  epochs?: readonly EpochOut[];
};

/** The chosen category and its ancestors, from the top level down; empty if none is chosen. */
export function categoryTrail(categories: readonly CategoryOut[], slug: string | undefined): CategoryOut[] {
  const byId = new Map(categories.map((category) => [category.id, category]));
  const trail: CategoryOut[] = [];
  let current = categories.find((category) => category.slug === slug);
  while (current && !trail.includes(current)) {
    trail.unshift(current);
    current = current.parent_id === null ? undefined : byId.get(current.parent_id);
  }
  return trail;
}

function childrenOf(categories: readonly CategoryOut[], parentId: string | null): CategoryOut[] {
  return categories
    .filter((category) => category.parent_id === parentId)
    .sort((a, b) => a.position - b.position || a.name.localeCompare(b.name, "de"));
}

/**
 * Gauge and category as links, so every filtered list has its own address (and
 * works without JavaScript). The top-level categories come first; once one is
 * chosen, its subcategories follow in a row of their own. A category includes its
 * subcategories.
 */
export function CatalogFilters({ query, scales, categories, epochs = [] }: CatalogFiltersProps) {
  const topLevel = childrenOf(categories, null);
  const trail = categoryTrail(categories, query.kategorie);
  // One row of subcategories for every chosen category that has some.
  const levels = trail
    .map((parent, depth) => ({ parent, children: childrenOf(categories, parent.id), chosen: trail[depth + 1] }))
    .filter((level) => level.children.length > 0);
  return (
    <div className="space-y-6">
      <nav aria-label="Spurweite">
        <p className="label-caps text-ink-tertiary">Spurweite</p>
        <ul className="mt-3 flex flex-wrap gap-2">
          <li>
            <FilterLink href={catalogHref({ ...query, spur: undefined })} active={!query.spur}>
              Alle
            </FilterLink>
          </li>
          {scales.map((scale) => (
            <li key={scale.code}>
              <FilterLink
                href={catalogHref({ ...query, spur: scale.code })}
                active={query.spur === scale.code}
              >
                {scale.name}
              </FilterLink>
            </li>
          ))}
        </ul>
      </nav>
      {topLevel.length > 0 ? (
        <nav aria-label="Kategorie">
          <p className="label-caps text-ink-tertiary">Kategorie</p>
          <ul className="mt-3 flex flex-wrap gap-2">
            <li>
              <FilterLink href={catalogHref({ ...query, kategorie: undefined })} active={trail.length === 0}>
                Alle
              </FilterLink>
            </li>
            {topLevel.map((category) => (
              <li key={category.id}>
                <FilterLink
                  href={catalogHref({ ...query, kategorie: category.slug })}
                  active={trail[0]?.id === category.id}
                  current={query.kategorie === category.slug}
                >
                  {category.name}
                </FilterLink>
              </li>
            ))}
          </ul>
          {levels.map(({ parent, children, chosen }) => (
            <ul
              key={parent.id}
              aria-label={`Unterkategorien von ${parent.name}`}
              className="mt-3 ml-1 flex flex-wrap gap-2 border-l border-line-strong pl-3"
            >
              <li>
                <FilterLink
                  href={catalogHref({ ...query, kategorie: parent.slug })}
                  active={chosen === undefined}
                  aria-label={`Alles in ${parent.name}`}
                >
                  Alle
                </FilterLink>
              </li>
              {children.map((category) => (
                <li key={category.id}>
                  <FilterLink
                    href={catalogHref({ ...query, kategorie: category.slug })}
                    active={chosen?.id === category.id}
                  >
                    {category.name}
                  </FilterLink>
                </li>
              ))}
            </ul>
          ))}
        </nav>
      ) : null}
      {epochs.length > 0 ? (
        <nav aria-label="Epoche">
          <p className="label-caps text-ink-tertiary">Epoche</p>
          <ul className="mt-3 flex flex-wrap gap-2">
            <li>
              <FilterLink href={catalogHref({ ...query, epoche: undefined })} active={!query.epoche}>
                Alle
              </FilterLink>
            </li>
            {epochs.map((epoch) => (
              <li key={epoch.code}>
                <FilterLink
                  href={catalogHref({ ...query, epoche: epoch.code })}
                  active={query.epoche === epoch.code}
                  aria-label={`Epoche ${epoch.code}, ${epoch.period}`}
                  title={`${epoch.name} · ${epoch.period}`}
                >
                  {epoch.code}
                </FilterLink>
              </li>
            ))}
          </ul>
        </nav>
      ) : null}
    </div>
  );
}

/** The order of the list as a row of links; choosing one starts at the first page again. */
export function CatalogSort({ query, className }: { query: CatalogQuery; className?: string }) {
  const current = sortFor(query.sortierung);
  return (
    <nav aria-label="Sortierung" className={cn("flex flex-wrap items-baseline gap-x-5 gap-y-2 text-small", className)}>
      <span className="label-caps text-ink-tertiary" aria-hidden="true">
        Sortieren
      </span>
      {CATALOG_SORTS.map((entry) => (
        <Link
          key={entry.sort}
          href={catalogHref({ ...query, sortierung: entry.param })}
          aria-current={entry.sort === current ? "page" : undefined}
          className={cn(
            "border-b py-1 transition-colors",
            entry.sort === current
              ? "border-selected font-medium text-ink"
              : "border-transparent text-ink-secondary hover:border-line-strong hover:text-ink",
          )}
        >
          {entry.label}
        </Link>
      ))}
    </nav>
  );
}
