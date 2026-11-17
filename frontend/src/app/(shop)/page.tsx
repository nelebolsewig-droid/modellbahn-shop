import type { Route } from "next";
import Link from "next/link";
import { connection } from "next/server";

import { ScaleGates } from "@/components/shop/scale-gates";
import { HomeActions } from "@/components/site/home-actions";
import { NextFair } from "@/components/site/next-fair";
import { ProductCard } from "@/components/ui/product-card";
import { Reveal } from "@/components/ui/reveal";
import { MakingOfTeaser } from "@/components/workshop/making-of-teaser";
import { ModelTurntable } from "@/components/workshop/model-turntable";
import type {
  FairCalendarOut,
  FairOut,
  NavigationOut,
  StoreProductCardOut,
  StoreProductPageOut,
} from "@/lib/api/generated/model";
import { fetchStore } from "@/lib/api/server";
import { loadNavigation } from "@/lib/catalog/store-data";
import { EDK6_MODEL } from "@/lib/workshop/edk6-model";

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

const HERO_FIGURES = [
  { value: "1992", label: "gegründet", tone: "text-sun" },
  { value: "12", label: "Drucker", tone: "text-on-night" },
  { value: "N–0", label: "Maßstäbe", tone: "text-on-night" },
] as const;

const TICKER = [
  "Resin-Druck",
  "Handarbeit",
  "Kleinserie",
  "H0 · 1:87",
  "TT · 1:120",
  "Autokrane",
  "Lkw",
  "Schienenfahrzeuge",
  "Sonderanfertigung",
  "Seit 1992",
] as const;

// The traits' cards, one colour of the palette each.
const TRAIT_TONES = [
  { card: "bg-highlight-subtle", ink: "text-highlight-ink", rule: "bg-highlight-fill" },
  { card: "bg-plum-subtle", ink: "text-plum", rule: "bg-plum" },
  { card: "bg-sea-subtle", ink: "text-sea", rule: "bg-sea" },
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
      {/* The hero: a night-blue stage with the palette's glows drifting behind the workshop's
          own crane, which turns in its paint and comes apart under the pointer. */}
      <section className="px-3 pt-3 sm:px-5 sm:pt-5">
        <div className="relative mx-auto max-w-[88rem] overflow-hidden rounded-lg bg-night text-on-night">
          <span aria-hidden="true" className="absolute -top-40 -right-24 size-[34rem] animate-drift rounded-full bg-highlight opacity-45 blur-[90px]" />
          <span aria-hidden="true" className="absolute -bottom-52 left-[18%] size-[30rem] animate-drift-slow rounded-full bg-plum opacity-55 blur-[100px]" />
          <span aria-hidden="true" className="absolute top-1/3 -left-40 size-[24rem] animate-drift rounded-full bg-sea opacity-45 blur-[90px]" />
          {/* The drawing sheet's grid, faint, fading out towards the edges. */}
          <span
            aria-hidden="true"
            className="absolute inset-0 bg-[image:linear-gradient(rgb(255_255_255_/_0.07)_1px,transparent_1px),linear-gradient(90deg,rgb(255_255_255_/_0.07)_1px,transparent_1px)] bg-[size:32px_32px] [mask-image:radial-gradient(ellipse_at_center,black_30%,transparent_78%)]"
          />
          <div className="relative mx-auto grid max-w-6xl items-center gap-6 px-6 py-14 sm:px-10 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)] lg:gap-10 lg:py-20">
            <div>
              <p className="inline-flex animate-rise-in items-center gap-2.5 rounded-full border border-on-night/20 bg-on-night/10 px-3.5 py-1.5 label-caps text-on-night backdrop-blur">
                <span aria-hidden="true" className="size-2 animate-lamp-glow rounded-full bg-sun" />
                Seit 1992 · Handarbeit aus Deutschland
              </p>
              <h1 className="mt-7 animate-rise-in text-[2.75rem] leading-[1.02] font-semibold tracking-[-0.035em] [animation-delay:80ms] sm:text-[4.25rem] lg:text-[4.75rem]">
                Jedes Modell ein <span className="text-spectrum-night">Unikat.</span>
              </h1>
              <p className="mt-6 max-w-xl animate-rise-in text-body-lg text-on-night-muted [animation-delay:200ms]">
                Gefertigt mit Liebe zum Detail: Fahrzeugmodelle in Kleinserie für Sammler und Modellbahner. Lkw,
                Autokrane und Schienenfahrzeuge von N bis Spur 0. Bestellen kannst du als Gast oder mit Kundenkonto.
              </p>
              <HomeActions />
              <dl className="mt-12 grid max-w-lg animate-rise-in grid-cols-3 gap-3 [animation-delay:440ms]">
                {HERO_FIGURES.map((figure) => (
                  <div key={figure.label} className="rounded-md border border-on-night/15 bg-on-night/[0.07] px-4 py-3 backdrop-blur">
                    <dt className="order-2 text-hint text-on-night-muted">{figure.label}</dt>
                    <dd className={`text-heading font-semibold tracking-[-0.02em] tabular-nums ${figure.tone}`}>{figure.value}</dd>
                  </div>
                ))}
              </dl>
            </div>
            <div className="relative">
              <ModelTurntable model={EDK6_MODEL} ground="night" zoom={1.5} className="aspect-square lg:aspect-[4/5]" />
              <p aria-hidden="true" className="pointer-events-none absolute right-2 bottom-2 rounded-full border border-on-night/20 bg-on-night/10 px-3 py-1 font-mono text-hint text-on-night-muted backdrop-blur max-sm:hidden">
                EDK 6 · aus unseren Druckdateien · fass ihn an
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* A band of words in the palette, running. Decorative: the same words are in the page. */}
      <div aria-hidden="true" className="mt-3 overflow-hidden bg-spectrum py-3 text-on-highlight sm:mt-5">
        <div className="flex w-max animate-ticker gap-10 pr-10 text-small font-semibold tracking-[0.08em] whitespace-nowrap uppercase">
          {[...TICKER, ...TICKER].map((word, index) => (
            <span key={index} className="flex items-center gap-10">
              {word}
              <span className="size-1.5 rounded-full bg-on-highlight" />
            </span>
          ))}
        </div>
      </div>

      {fair ? <NextFair fair={fair} /> : null}

      {newest.length > 0 ? (
        <section aria-labelledby="neu">
          <div className="mx-auto max-w-6xl px-5 py-16 sm:px-8 lg:py-24">
            <div className="flex flex-wrap items-baseline justify-between gap-4">
              <h2 id="neu" className="text-title font-semibold tracking-[-0.03em]">
                Neu aus der <span className="text-spectrum">Werkstatt</span>
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
        <section aria-labelledby="massstaebe">
          <div className="mx-auto max-w-6xl px-5 py-16 sm:px-8 lg:py-24">
            <div className="flex flex-wrap items-baseline justify-between gap-4">
              <h2 id="massstaebe" className="text-title font-semibold tracking-[-0.03em]">
                Nach <span className="text-spectrum">Maßstab</span>
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

      <section aria-labelledby="was-uns-ausmacht">
        <div className="mx-auto max-w-6xl px-5 py-16 sm:px-8 lg:py-24">
          <h2 id="was-uns-ausmacht" className="text-title font-semibold tracking-[-0.03em]">
            Was uns <span className="text-spectrum">ausmacht</span>
          </h2>
          <ul className="mt-10 grid gap-5 sm:grid-cols-3">
            {TRAITS.map((item, index) => (
              <Reveal
                as="li"
                key={item.title}
                index={index}
                className={`group relative overflow-hidden rounded-lg p-7 transition-[transform,box-shadow] duration-300 ease-settle hover:-translate-y-1 hover:shadow-lift ${TRAIT_TONES[index % TRAIT_TONES.length]?.card}`}
              >
                <span
                  aria-hidden="true"
                  className={`absolute top-0 left-0 h-1 w-14 transition-[width] duration-500 ease-settle group-hover:w-full ${TRAIT_TONES[index % TRAIT_TONES.length]?.rule}`}
                />
                <p className={`text-display leading-none font-semibold tracking-[-0.04em] tabular-nums ${TRAIT_TONES[index % TRAIT_TONES.length]?.ink}`}>
                  {String(index + 1).padStart(2, "0")}
                </p>
                <h3 className="mt-5 text-[1.25rem] leading-7 font-semibold tracking-[-0.01em]">{item.title}</h3>
                <p className="mt-3 text-ink">{item.text}</p>
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
