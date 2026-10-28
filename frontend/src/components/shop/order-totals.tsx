import type { ShippingCountryOut, TotalsOut } from "@/lib/api/generated/model";
import { formatPrice } from "@/lib/catalog/format";
import { missingForFreeShipping } from "@/lib/sales/totals";
import { cn } from "@/lib/utils";

type OrderTotalsProps = {
  totals: TotalsOut;
  /** "Deutschland": where the shipping goes. */
  countryName: string;
  className?: string;
};

const ROW = "col-span-2 grid grid-cols-subgrid";

/** Goods, shipping, total and the VAT contained in it, aligned on the right. */
export function OrderTotals({ totals, countryName, className }: OrderTotalsProps) {
  return (
    // Each row a subgrid on the same two columns: the amounts line up, and the rule
    // above the total runs unbroken across both.
    <dl className={cn("grid grid-cols-[minmax(0,1fr)_auto] gap-x-6 gap-y-2 text-small", className)}>
      <div className={ROW}>
        <dt className="text-ink-secondary">Zwischensumme</dt>
        <dd className="text-right tabular-nums">{formatPrice(totals.subtotal_cents)}</dd>
      </div>
      <div className={ROW}>
        <dt className="text-ink-secondary">Versand nach {countryName}</dt>
        <dd className="text-right tabular-nums">
          {totals.shipping_cents === 0 ? "kostenlos" : formatPrice(totals.shipping_cents)}
        </dd>
      </div>
      <div className={cn(ROW, "mt-3 items-baseline border-t border-line pt-3")}>
        <dt className="text-body font-medium">Summe</dt>
        <dd className="text-right text-heading tabular-nums">{formatPrice(totals.total_cents)}</dd>
      </div>
      <div className={ROW}>
        <dt className="text-hint text-ink-tertiary">darin enthalten 19 % MwSt.</dt>
        <dd className="text-right text-hint text-ink-tertiary tabular-nums">{formatPrice(totals.tax_cents)}</dd>
      </div>
    </dl>
  );
}

type FreeShippingMeterProps = {
  country: ShippingCountryOut;
  subtotalCents: number;
  className?: string;
};

/**
 * How far the cart is from free shipping, as a stretch of track that fills up:
 * the sleepers stay, the rails turn black as the goods add up.
 */
export function FreeShippingMeter({ country, subtotalCents, className }: FreeShippingMeterProps) {
  const missing = missingForFreeShipping(country, subtotalCents);
  // Nothing to fill up where shipping is never free.
  if (subtotalCents === 0 || missing === null || country.free_from_cents === null) {
    return null;
  }
  const share = Math.min(1, subtotalCents / country.free_from_cents);
  return (
    <div className={className}>
      <p className="text-hint text-ink-secondary">
        {missing === 0 ? (
          <>Der Versand nach {country.name} ist kostenlos.</>
        ) : (
          <>
            Noch <span className="font-medium text-ink tabular-nums">{formatPrice(missing)}</span> bis zum
            kostenlosen Versand nach {country.name}.
          </>
        )}
      </p>
      <div
        role="meter"
        aria-label="Weg zum kostenlosen Versand"
        aria-valuemin={0}
        aria-valuemax={country.free_from_cents}
        aria-valuenow={Math.min(subtotalCents, country.free_from_cents)}
        aria-valuetext={missing === 0 ? "erreicht" : `noch ${formatPrice(missing)}`}
        className="relative mt-2.5 h-3"
      >
        {/* Sleepers */}
        <div
          aria-hidden="true"
          className="absolute inset-0 bg-[repeating-linear-gradient(90deg,var(--color-line-strong)_0_2px,transparent_2px_10px)] opacity-70"
        />
        {/* Rails: grey, and black as far as the cart reaches */}
        {["top-0.5", "bottom-0.5"].map((edge) => (
          <div key={edge} aria-hidden="true" className={cn("absolute inset-x-0 h-px bg-line-strong", edge)}>
            <div
              className="h-px bg-selected transition-[width] duration-500 ease-out"
              style={{ width: `${share * 100}%` }}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
