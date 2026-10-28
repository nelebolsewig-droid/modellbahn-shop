"use client";

import { PendingNotice } from "@/components/ui/pending-notice";
import { formatPrice } from "@/lib/catalog/format";
import { useCart } from "@/lib/sales/cart";
import { shippingGroups } from "@/lib/sales/countries";

/** The shipping rates, as the backend charges them: one row per set of terms. */
export function ShippingRates() {
  const cart = useCart();
  if (!cart.data) {
    return cart.isError ? null : <PendingNotice>Die Versandkosten werden geladen …</PendingNotice>;
  }
  const groups = shippingGroups(cart.data.countries);
  const anyFree = cart.data.countries.some((country) => country.free_from_cents !== null);
  return (
    <table className="w-full max-w-2xl text-left text-small">
      <caption className="sr-only">Versandkosten nach Land</caption>
      <thead>
        <tr className="border-b border-line-strong">
          <th scope="col" className="py-3 pr-4 font-medium">Wohin</th>
          <th scope="col" className="py-3 pr-4 text-right font-medium">Versand je Bestellung</th>
          {anyFree ? <th scope="col" className="py-3 text-right font-medium">Kostenlos ab</th> : null}
        </tr>
      </thead>
      <tbody>
        {groups.map((group) => {
          const first = group[0];
          if (first === undefined) {
            return null;
          }
          return (
            <tr key={first.code} className="border-b border-line align-top">
              <th scope="row" className="py-3 pr-4 font-normal">
                {group.length === 1 ? (
                  first.name
                ) : (
                  <>
                    <span className="block">Übrige EU-Länder</span>
                    <span className="mt-1 block text-hint text-ink-tertiary">
                      {group.map((country) => country.name).join(", ")}
                    </span>
                  </>
                )}
              </th>
              <td className="py-3 pr-4 text-right tabular-nums">{formatPrice(first.rate_cents)}</td>
              {anyFree ? (
                <td className="py-3 text-right tabular-nums">
                  {first.free_from_cents === null ? "–" : formatPrice(first.free_from_cents)}
                </td>
              ) : null}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
