import type { Metadata, Route } from "next";
import Link from "next/link";
import { connection } from "next/server";

import { ScaleGates } from "@/components/shop/scale-gates";
import { HomeActions } from "@/components/site/home-actions";
import { JsonLd } from "@/components/site/json-ld";
import { NextFair } from "@/components/site/next-fair";
import { SloganBand } from "@/components/site/slogan-band";
import { ScrollFilm } from "@/components/site/scroll-film/scroll-film";
import { ProductCard } from "@/components/ui/product-card";
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
import { finishName } from "@/components/ui/photo-mark";
import { SHOP_NAME } from "@/lib/config";
import { loadImprint } from "@/lib/site/imprint";
import { publicBaseUrl } from "@/lib/site/sitemap";
import { storeJsonLd } from "@/lib/site/structured-data";

// The words people search for (ADR 0051): what the models are and what they are for.
export const metadata: Metadata = {
  title: { absolute: `${SHOP_NAME} – Fahrzeugmodelle für die Modellbahn aus dem 3D-Druck` },
  description:
    "Handgefertigte Resin-Modelle in Kleinserie: Lkw, Autokrane, Pkw und Schienenfahrzeuge nach DDR-Vorbild für Modellbahn und Sammler.",
};

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
  const [newest, navigation, fair, imprint] = await Promise.all([
    newestProducts(),
    navigationOrNull(),
    nextFair(),
    loadImprint(),
  ]);
  const scaleNames = new Map((navigation?.scales ?? []).map((scale) => [scale.code, scale.name]));
  return (
    <>
      <JsonLd data={storeJsonLd(imprint, publicBaseUrl(), SHOP_NAME)} />
      <ScrollFilm actions={<HomeActions />} />

      <SloganBand />

      {fair ? <NextFair fair={fair} /> : null}

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
                    priceVaries={item.price_varies}
                    image={item.image}
                    finishes={item.finish_codes.map(finishName)}
                    label={item.label}
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

      <MakingOfTeaser />

      <section aria-labelledby="was-uns-ausmacht" className="bg-stage">
        <div className="mx-auto max-w-6xl px-5 py-16 sm:px-8 lg:py-24">
          <h2 id="was-uns-ausmacht" className="text-heading">
            Was uns ausmacht
          </h2>
          <ul className="mt-10 grid gap-10 sm:grid-cols-3 sm:gap-12">
            {TRAITS.map((item) => (
              <li key={item.title} className="border-t border-line-strong pt-6">
                <h3 className="text-[1.25rem] leading-7 font-normal tracking-[-0.01em]">{item.title}</h3>
                <p className="mt-3 text-ink-secondary">{item.text}</p>
                {item.link ? (
                  <Link href={item.link.href} className="mt-4 inline-block text-small font-medium text-accent hover:underline">
                    {item.link.label}
                  </Link>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      </section>
    </>
  );
}
