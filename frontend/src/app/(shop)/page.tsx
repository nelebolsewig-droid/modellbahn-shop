import type { Route } from "next";
import Link from "next/link";
import { connection } from "next/server";

import { ScaleGates } from "@/components/shop/scale-gates";
import { HomeActions } from "@/components/site/home-actions";
import { NextFair } from "@/components/site/next-fair";
import { CraneTruckDrawing } from "@/components/site/crane-truck-drawing";
import { ProductCard } from "@/components/ui/product-card";
import { Reveal } from "@/components/ui/reveal";
import { MakingOfTeaser } from "@/components/workshop/making-of-teaser";
import type {
  FairCalendarOut,
  FairOut,
  NavigationOut,
  StoreProductCardOut,
  StoreProductPageOut,
} from "@/lib/api/generated/model";
import { fetchStore } from "@/lib/api/server";
import { loadNavigation } from "@/lib/catalog/store-data";

// What sets the workshop apart, from its own website (Über uns, Sonderanfertigung).
const TRAITS = [
  {
    title: "Kleinserie statt Fließband",
    text: "Jedes Modell entsteht in Handarbeit und limitierter Auflage – mit einem Blick fürs Detail, der bei Massenware verloren geht.",
    link: null,
  },
  {
    title: "Gefertigt, wenn du bestellst",
    text: "Manche Modelle bauen wir erst für dich. Ob ein Modell vorrätig ist und wann es ankommt, siehst du vor dem Kauf.",
    link: null,
  },
  {
    title: "Dein eigenes Modell",
    text: "Sonderanfertigungen im 3D-Druck und Lasercutting, vom Einzelstück bis zur Kleinserie.",
    link: { href: "/sonderanfertigung", label: "Mehr zur Sonderanfertigung" },
  },
] as const satisfies readonly { title: string; text: string; link: { href: Route; label: string } | null }[];

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

/** The next fair still to come; null if none is planned or the API is unreachable. */
async function nextFair(): Promise<FairOut | null> {
  try {
    const calendar = await fetchStore<FairCalendarOut>("/fairs");
    return calendar?.upcoming[0] ?? null;
  } catch {
    return null;
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
  const [newest, navigation, fair] = await Promise.all([newestProducts(), navigationOrNull(), nextFair()]);
  const scaleNames = new Map((navigation?.scales ?? []).map((scale) => [scale.code, scale.name]));
  return (
    <>
      <section className="mx-auto grid max-w-6xl items-center gap-14 px-5 pt-14 pb-20 sm:px-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:gap-20 lg:pt-24 lg:pb-32">
        <div>
          <p className="animate-rise-in label-caps label-tick text-ink-tertiary">Seit 1992 · Handarbeit aus Deutschland</p>
          <h1 className="mt-5 animate-rise-in text-title [animation-delay:80ms] sm:text-display">
            Jedes Modell ein{" "}
            <span className="relative inline-block">
              Unikat
              {/* The stroke under the word draws itself once, in signal orange. */}
              <span
                aria-hidden="true"
                className="absolute inset-x-0 -bottom-1 h-[0.09em] origin-left animate-stroke-in rounded-full bg-highlight"
              />
            </span>{" "}
            – gefertigt mit Liebe zum Detail.
          </h1>
          <p className="mt-6 max-w-xl animate-rise-in text-body-lg text-ink-secondary [animation-delay:200ms]">
            Fahrzeugmodelle in Kleinserie für Sammler und Modellbahner: Lkw, Autokrane und
            Schienenfahrzeuge von N bis Spur 0. Bestellen kannst du als Gast oder mit Kundenkonto.
          </p>
          <HomeActions />
        </div>
        <CraneTruckDrawing className="mx-auto w-full max-w-xl lg:max-w-none" />
      </section>

      {fair ? <NextFair fair={fair} /> : null}

      {newest.length > 0 ? (
        <section aria-labelledby="neu" className="border-t border-line">
          <div className="mx-auto max-w-6xl px-5 py-16 sm:px-8 lg:py-24">
            <div className="flex flex-wrap items-baseline justify-between gap-4">
              <h2 id="neu" className="text-heading">
                Neu aus der Werkstatt
              </h2>
              <Link href="/katalog" className="link-sweep text-small font-medium text-accent hover:text-highlight-ink">
                Alle Modelle
              </Link>
            </div>
            <ul className="mt-10 grid gap-x-8 gap-y-12 sm:grid-cols-2 lg:grid-cols-3">
              {newest.map((item, index) => (
                <Reveal as="li" key={item.slug} index={index}>
                  <ProductCard
                    href={`/produkte/${item.slug}` as Route}
                    name={item.name}
                    summary={item.summary}
                    scales={item.scale_codes.map((code) => scaleNames.get(code) ?? code)}
                    priceFromCents={item.price_from_cents}
                    image={item.image}
                  />
                </Reveal>
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
            <Reveal className="mt-10">
              <ScaleGates scales={navigation.scales} />
            </Reveal>
          </div>
        </section>
      ) : null}

      <MakingOfTeaser />

      <section aria-labelledby="was-uns-ausmacht" className="bg-stage">
        <div className="mx-auto max-w-6xl px-5 py-16 sm:px-8 lg:py-24">
          <h2 id="was-uns-ausmacht" className="text-heading">
            Was uns ausmacht
          </h2>
          <ul className="mt-10 grid gap-10 sm:grid-cols-3 sm:gap-12">
            {TRAITS.map((item, index) => (
              <Reveal as="li" key={item.title} index={index} className="group relative border-t border-line-strong pt-6">
                {/* The rule above each trait lights up in signal orange under the pointer. */}
                <span
                  aria-hidden="true"
                  className="absolute -top-px left-0 h-0.5 w-10 bg-highlight transition-[width] duration-500 ease-settle group-hover:w-full"
                />
                <p className="font-mono text-hint text-highlight-ink">{String(index + 1).padStart(2, "0")}</p>
                <h3 className="mt-2 text-[1.25rem] leading-7 font-normal tracking-[-0.01em]">{item.title}</h3>
                <p className="mt-3 text-ink-secondary">{item.text}</p>
                {item.link ? (
                  <Link href={item.link.href} className="mt-4 inline-block link-sweep text-small font-medium text-accent hover:text-highlight-ink">
                    {item.link.label}
                  </Link>
                ) : null}
              </Reveal>
            ))}
          </ul>
        </div>
      </section>
    </>
  );
}
