import Link from "next/link";

/** The workshop's slogan, set big with a layered edge; between the scroll film and the shop. */
export function SloganBand() {
  return (
    <section aria-label="Unser Motto" className="overflow-hidden border-t border-line bg-stage">
      <div className="mx-auto max-w-6xl px-5 py-20 sm:px-8 lg:py-28">
        <p className="scroll-rise label-caps text-accent">Unser Motto</p>
        <p className="scroll-rise mt-6 font-display text-[2.6rem] leading-[0.95] font-extrabold tracking-[-0.04em] text-balance sm:text-[4.5rem] lg:text-[6rem]">
          Modellbau ist mehr als ein Hobby.
          <span className="slogan-depth mt-2 block text-ink">Baue, was du liebst.</span>
        </p>
        <div className="scroll-rise mt-10 flex flex-wrap gap-x-8 gap-y-3 text-small font-medium">
          <Link href="/der-weg-zum-perfekten-modell" className="text-accent hover:underline">
            Der Weg zum perfekten Modell →
          </Link>
          <Link href="/in-planung" className="text-ink-secondary hover:text-ink hover:underline">
            Was ist in Planung? →
          </Link>
        </div>
      </div>
    </section>
  );
}
