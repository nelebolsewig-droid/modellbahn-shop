import Link from "next/link";
import type { Route } from "next";

import type { CategoryOut, ScaleOut } from "@/lib/api/generated/model";
import { cn } from "@/lib/utils";

export type CatalogQuery = { spur?: string; kategorie?: string; suche?: string };

/**
 * The catalogue's address for a combination of filters (empty ones are left out);
 * `weiter` is the cursor of the next page.
 */
export function catalogHref(query: CatalogQuery & { weiter?: string }): Route {
  const params = new URLSearchParams();
  for (const [name, value] of Object.entries(query)) {
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
};

function FilterLink({ href, active, current = active, children, "aria-label": label }: FilterLinkProps) {
  return (
    <Link
      href={href}
      aria-current={current ? "page" : undefined}
      aria-label={label}
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
export function CatalogFilters({ query, scales, categories }: CatalogFiltersProps) {
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
    </div>
  );
}
