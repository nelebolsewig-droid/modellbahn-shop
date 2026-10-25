import Link from "next/link";
import type { Route } from "next";

import type {
  EpochOut,
  ListStoreProductsSort,
  NavigationCategoryOut,
  NavigationScaleOut,
} from "@/lib/api/generated/model";
import { branchCount, catalogPath, scaleLabel, type CatalogLocation } from "@/lib/catalog/scales";
import { cn } from "@/lib/utils";

/*
 * The navigation of a scale's list (/katalog/h0/…): categories as a tree, epoch,
 * order and the other scales. Everything is a link, so every list has its own address
 * and works without JavaScript.
 */

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

type TreeNode = { id: string; parent_id: string | null; slug: string };

/** The chosen category and its ancestors, from the top level down; empty if none is chosen. */
export function categoryTrail<T extends TreeNode>(categories: readonly T[], slug: string | undefined): T[] {
  const byId = new Map(categories.map((category) => [category.id, category]));
  const trail: T[] = [];
  let current = categories.find((category) => category.slug === slug);
  while (current && !trail.includes(current)) {
    trail.unshift(current);
    current = current.parent_id === null ? undefined : byId.get(current.parent_id);
  }
  return trail;
}

type FilterLinkProps = {
  href: Route;
  active: boolean;
  children: string;
  "aria-label"?: string;
  title?: string;
};

function FilterLink({ href, active, children, "aria-label": label, title }: FilterLinkProps) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      aria-label={label}
      title={title}
      className={cn(
        "inline-flex h-10 items-center rounded-full border px-4 text-sm font-medium transition-colors duration-150",
        active ? "border-selected bg-selected text-on-selected" : "border-line-strong bg-surface text-ink hover:border-ink",
      )}
    >
      {children}
    </Link>
  );
}

type CategoryTreeProps = {
  location: CatalogLocation;
  categories: readonly NavigationCategoryOut[];
};

/**
 * The categories that have models in this scale, as a branching track: the top level
 * first, the chosen branch opens below its category. Counts include subcategories.
 */
export function CategoryTree({ location, categories }: CategoryTreeProps) {
  const count = (category: NavigationCategoryOut) => branchCount(categories, category.id, location.scale);
  const offered = (parent: string | null) =>
    categories
      .filter((category) => category.parent_id === parent && count(category) > 0)
      .sort((a, b) => a.position - b.position || a.name.localeCompare(b.name, "de"));
  const trail = categoryTrail(categories, location.category);
  const open = new Set(trail.map((category) => category.id));
  const total = categories.reduce((sum, category) => sum + (category.product_counts[location.scale] ?? 0), 0);

  function branch(parent: string | null, depth: number) {
    const items = offered(parent);
    if (items.length === 0) {
      return null;
    }
    return (
      <ul className={cn(depth > 0 && "mt-1 ml-3 border-l border-line-strong pl-3")}>
        {items.map((category) => {
          const current = location.category === category.slug;
          return (
            <li key={category.id}>
              <Link
                href={catalogPath({ ...location, category: category.slug, weiter: undefined })}
                aria-current={current ? "page" : undefined}
                className={cn(
                  "flex items-baseline justify-between gap-3 rounded-sm py-1.5 text-small transition-colors",
                  current ? "font-medium text-ink" : open.has(category.id) ? "text-ink" : "text-ink-secondary hover:text-ink",
                )}
              >
                <span className="flex items-center gap-2">
                  {/* A signal lamp marks where the list stands. */}
                  <span
                    aria-hidden="true"
                    className={cn("size-1.5 shrink-0 rounded-full", current ? "bg-accent" : "bg-transparent")}
                  />
                  {category.name}
                </span>
                <span className="font-mono text-hint text-ink-tertiary tabular-nums">{count(category)}</span>
              </Link>
              {open.has(category.id) ? branch(category.id, depth + 1) : null}
            </li>
          );
        })}
      </ul>
    );
  }

  return (
    <nav aria-label="Kategorie">
      <p className="label-caps text-ink-tertiary">Kategorie</p>
      <div className="mt-3">
        <Link
          href={catalogPath({ ...location, category: undefined, weiter: undefined })}
          aria-current={location.category ? undefined : "page"}
          className={cn(
            "flex items-baseline justify-between gap-3 py-1.5 text-small",
            location.category ? "text-ink-secondary hover:text-ink" : "font-medium text-ink",
          )}
        >
          <span className="flex items-center gap-2">
            <span aria-hidden="true" className={cn("size-1.5 rounded-full", location.category ? "bg-transparent" : "bg-accent")} />
            Alle Kategorien
          </span>
          <span className="font-mono text-hint text-ink-tertiary tabular-nums">{total}</span>
        </Link>
        {branch(null, 0)}
      </div>
    </nav>
  );
}

/** The epoch as pills; "Alle" lifts the filter. */
export function EpochFilter({ location, epochs }: { location: CatalogLocation; epochs: readonly EpochOut[] }) {
  if (epochs.length === 0) {
    return null;
  }
  return (
    <nav aria-label="Epoche">
      <p className="label-caps text-ink-tertiary">Epoche</p>
      <ul className="mt-3 flex flex-wrap gap-2">
        <li>
          <FilterLink href={catalogPath({ ...location, epoche: undefined, weiter: undefined })} active={!location.epoche}>
            Alle
          </FilterLink>
        </li>
        {epochs.map((epoch) => (
          <li key={epoch.code}>
            <FilterLink
              href={catalogPath({ ...location, epoche: epoch.code, weiter: undefined })}
              active={location.epoche === epoch.code}
              aria-label={`Epoche ${epoch.code}, ${epoch.period}`}
              title={`${epoch.name} · ${epoch.period}`}
            >
              {epoch.code}
            </FilterLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/** The order of the list as a row of links; choosing one starts at the first page again. */
export function CatalogSort({ location, className }: { location: CatalogLocation; className?: string }) {
  const current = sortFor(location.sortierung);
  return (
    <nav aria-label="Sortierung" className={cn("flex flex-wrap items-baseline gap-x-5 gap-y-2 text-small", className)}>
      <span className="label-caps text-ink-tertiary" aria-hidden="true">
        Sortieren
      </span>
      {CATALOG_SORTS.map((entry) => (
        <Link
          key={entry.sort}
          href={catalogPath({ ...location, sortierung: entry.param, weiter: undefined })}
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

type ScaleSwitchProps = {
  location: CatalogLocation;
  scales: readonly NavigationScaleOut[];
  categories: readonly NavigationCategoryOut[];
};

/**
 * The other scales with models. Switching keeps the category where the other scale has
 * models in it, and starts at its whole list otherwise.
 */
export function ScaleSwitch({ location, scales, categories }: ScaleSwitchProps) {
  const chosen = categories.find((category) => category.slug === location.category);
  const offered = scales.filter((scale) => scale.product_count > 0);
  if (offered.length < 2) {
    return null;
  }
  return (
    <nav aria-label="Maßstab wechseln">
      <ul className="flex flex-wrap gap-2">
        {offered.map((scale) => {
          const keeps = chosen !== undefined && branchCount(categories, chosen.id, scale.code) > 0;
          return (
            <li key={scale.code}>
              <FilterLink
                href={catalogPath({
                  scale: scale.code,
                  category: keeps ? location.category : undefined,
                  epoche: location.epoche,
                  sortierung: location.sortierung,
                })}
                active={scale.code === location.scale}
                aria-label={`Maßstab ${scaleLabel(scale)}`}
              >
                {scale.name}
              </FilterLink>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
