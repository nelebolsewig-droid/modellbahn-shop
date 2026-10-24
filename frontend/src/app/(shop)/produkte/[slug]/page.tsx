import type { Metadata, Route } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import { cache } from "react";

import { ProductView } from "@/components/shop/product-view";
import type { StoreProductOut } from "@/lib/api/generated/model";
import { fetchStore } from "@/lib/api/server";

// Metadata and page ask for the same product; React's cache makes it one request.
const loadProduct = cache(async (slug: string): Promise<StoreProductOut | null> => {
  await connection();
  return fetchStore<StoreProductOut>(`/products/${encodeURIComponent(slug)}`);
});

export async function generateMetadata({ params }: PageProps<"/produkte/[slug]">): Promise<Metadata> {
  const product = await loadProduct((await params).slug);
  if (product === null) {
    return { title: "Produkt nicht gefunden" };
  }
  const og = product.gallery[0]?.image.renditions.find((r) => r.name === "og" && r.format === "webp");
  return {
    title: product.name,
    description: product.summary || undefined,
    openGraph: og ? { images: [{ url: og.url, width: og.width, height: og.height }] } : undefined,
  };
}

export default async function ProductPage({ params }: PageProps<"/produkte/[slug]">) {
  const product = await loadProduct((await params).slug);
  if (product === null) {
    notFound();
  }
  const paragraphs = product.description.split(/\n{2,}/).filter(Boolean);

  return (
    <div className="mx-auto max-w-6xl px-5 py-10 sm:px-8 lg:py-14">
      <nav aria-label="Brotkrumen" className="mb-8">
        <ol className="flex flex-wrap items-center gap-2 text-hint text-ink-tertiary">
          <li>
            <Link href="/katalog" className="hover:text-ink">
              Katalog
            </Link>
          </li>
          {product.category_path.map((category) => (
            <li key={category.slug} className="flex items-center gap-2">
              <span aria-hidden="true">/</span>
              <Link href={`/katalog?kategorie=${category.slug}` as Route} className="hover:text-ink">
                {category.name}
              </Link>
            </li>
          ))}
        </ol>
      </nav>

      <ProductView product={product} />

      {paragraphs.length > 0 || product.prototype || product.epochs.length > 0 ? (
        <section aria-labelledby="beschreibung" className="mt-20 grid gap-10 border-t border-line pt-14 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] lg:gap-16">
          <div>
            <h2 id="beschreibung" className="text-heading">
              Über das Modell
            </h2>
            <div className="mt-6 max-w-2xl space-y-4 text-ink-secondary">
              {paragraphs.map((paragraph) => (
                <p key={paragraph} className="whitespace-pre-line">
                  {paragraph}
                </p>
              ))}
            </div>
          </div>
          <dl className="space-y-6 text-small">
            {product.prototype ? (
              <div>
                <dt className="label-caps text-ink-tertiary">Vorbild</dt>
                <dd className="mt-2">{product.prototype}</dd>
              </div>
            ) : null}
            {product.epochs.length > 0 ? (
              <div>
                <dt className="label-caps text-ink-tertiary">Epoche</dt>
                <dd className="mt-2 space-y-1">
                  {product.epochs.map((epoch) => (
                    <p key={epoch.code}>
                      {epoch.name} <span className="text-ink-tertiary">({epoch.period})</span>
                    </p>
                  ))}
                </dd>
              </div>
            ) : null}
          </dl>
        </section>
      ) : null}
    </div>
  );
}
