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

function FilterLink({ href, active, children }: { href: Route; active: boolean; children: string }) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
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

/**
 * Gauge and category as links, so every filtered list has its own address (and
 * works without JavaScript). Only top-level categories are offered; a category
 * includes its subcategories.
 */
export function CatalogFilters({ query, scales, categories }: CatalogFiltersProps) {
  const topLevel = categories.filter((category) => category.parent_id === null);
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
              <FilterLink
                href={catalogHref({ ...query, kategorie: undefined })}
                active={!query.kategorie}
              >
                Alle
              </FilterLink>
            </li>
            {topLevel.map((category) => (
              <li key={category.id}>
                <FilterLink
                  href={catalogHref({ ...query, kategorie: category.slug })}
                  active={query.kategorie === category.slug}
                >
                  {category.name}
                </FilterLink>
              </li>
            ))}
          </ul>
        </nav>
      ) : null}
    </div>
  );
}
