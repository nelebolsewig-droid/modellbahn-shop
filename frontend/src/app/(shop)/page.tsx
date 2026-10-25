import type { Route } from "next";
import Link from "next/link";
import { connection } from "next/server";

import { ScaleGates } from "@/components/shop/scale-gates";
import { HomeActions } from "@/components/site/home-actions";
import { SignalBoxDrawing } from "@/components/site/signal-box-drawing";
import { ProductCard } from "@/components/ui/product-card";
import type { NavigationOut, StoreProductCardOut, StoreProductPageOut } from "@/lib/api/generated/model";
import { fetchStore } from "@/lib/api/server";
import { loadNavigation } from "@/lib/catalog/store-data";

// What the concept plans for the next steps (docs/KONZEPT.md, "Fahrplan"); the
// start page says honestly that none of it is open yet.
const COMING = [
  {
    title: "Gedruckt, wenn du bestellst",
    text: "Was nicht am Lager liegt, plant die Werkstatt für den nächsten Druck ein; die Lieferzeit steht vorher fest.",
  },
  {
    title: "Bausätze mit Stückliste",
    text: "Du siehst vorher, welche Teile in der Schachtel liegen und was du selbst ergänzt.",
  },
  {
    title: "Verfügbarkeit",
    text: "Du siehst, ob ein Modell am Lager liegt oder für dich gedruckt wird, und wann es ankommt.",
  },
] as const;

const NEWEST_COUNT = "3";

/** The newest products in the shop; none (and no section) while the API is unreachable. */
async function newestProducts(): Promise<StoreProductCardOut[]> {
  try {
    const page = await fetchStore<StoreProductPageOut>("/products", { limit: NEWEST_COUNT });
    return page?.items ?? [];
  } catch {
    return [];
  }
}

/** Scales and counts for the scale tiles; none while the API is unreachable. */
async function navigationOrNull(): Promise<NavigationOut | null> {
  try {
    return await loadNavigation();
  } catch {
    return null;
  }
}

export default async function HomePage() {
  // Rendered per request, so a newly published model shows up at once.
  await connection();
  const [newest, navigation] = await Promise.all([newestProducts(), navigationOrNull()]);
  const scaleNames = new Map((navigation?.scales ?? []).map((scale) => [scale.code, scale.name]));
  return (
    <>
      <section className="mx-auto grid max-w-6xl items-center gap-14 px-5 pt-14 pb-20 sm:px-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:gap-20 lg:pt-24 lg:pb-32">
        <div>
          <p className="label-caps text-ink-tertiary">Gleis 1 · Im Aufbau</p>
          <h1 className="mt-5 text-title sm:text-display">
            Hier entsteht ein Shop für 3D-gedruckte Modellbahn-Artikel.
          </h1>
          <p className="mt-6 max-w-xl text-body-lg text-ink-secondary">
            Konstruiert, gedruckt und geprüft in unserer eigenen Werkstatt, von Z bis G und für
            die Straße in 1:24. Bestellen kannst du als Gast oder mit Kundenkonto.
          </p>
          <HomeActions />
        </div>
        <SignalBoxDrawing className="mx-auto w-full max-w-xl lg:max-w-none" />
      </section>

      {newest.length > 0 ? (
        <section aria-labelledby="neu" className="border-t border-line">
          <div className="mx-auto max-w-6xl px-5 py-16 sm:px-8 lg:py-24">
            <div className="flex flex-wrap items-baseline justify-between gap-4">
              <h2 id="neu" className="text-heading">
                Neu aus der Werkstatt
              </h2>
              <Link href="/katalog" className="text-small font-medium text-accent hover:underline">
                Alle Modelle
              </Link>
            </div>
            <ul className="mt-10 grid gap-x-8 gap-y-12 sm:grid-cols-2 lg:grid-cols-3">
              {newest.map((item) => (
                <li key={item.slug}>
                  <ProductCard
                    href={`/produkte/${item.slug}` as Route}
                    name={item.name}
                    summary={item.summary}
                    scales={item.scale_codes.map((code) => scaleNames.get(code) ?? code)}
                    priceFromCents={item.price_from_cents}
                    image={item.image}
                  />
                </li>
              ))}
            </ul>
          </div>
        </section>
      ) : null}

      {navigation ? (
        <section aria-labelledby="massstaebe" className="border-t border-line">
          <div className="mx-auto max-w-6xl px-5 py-16 sm:px-8 lg:py-24">
            <div className="flex flex-wrap items-baseline justify-between gap-4">
              <h2 id="massstaebe" className="text-heading">
                Nach Maßstab
              </h2>
              <p className="text-small text-ink-tertiary">Ein Meter Vorbild, in jedem Maßstab nachgemessen</p>
            </div>
            <div className="mt-10">
              <ScaleGates scales={navigation.scales} />
            </div>
          </div>
        </section>
      ) : null}

      <section aria-labelledby="was-hier-entsteht" className="bg-stage">
        <div className="mx-auto max-w-6xl px-5 py-16 sm:px-8 lg:py-24">
          <h2 id="was-hier-entsteht" className="text-heading">
            Was hier entsteht
          </h2>
          <ul className="mt-10 grid gap-10 sm:grid-cols-3 sm:gap-12">
            {COMING.map((item) => (
              <li key={item.title} className="border-t border-line-strong pt-6">
                <h3 className="text-[1.25rem] leading-7 font-normal tracking-[-0.01em]">{item.title}</h3>
                <p className="mt-3 text-ink-secondary">{item.text}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </>
  );
}
