"use client";

import { PendingNotice } from "@/components/ui/pending-notice";
import { formatPrice } from "@/lib/catalog/format";
import { useCart } from "@/lib/sales/cart";

/** The shipping rates per country, as the backend charges them. */
export function ShippingRates() {
  const cart = useCart();
  if (!cart.data) {
    return cart.isError ? null : <PendingNotice>Die Versandkosten werden geladen …</PendingNotice>;
  }
  return (
    <table className="w-full max-w-xl text-left text-small">
      <caption className="sr-only">Versandkosten nach Land</caption>
      <thead>
        <tr className="border-b border-line-strong">
          <th scope="col" className="py-3 pr-4 font-medium">Land</th>
          <th scope="col" className="py-3 pr-4 text-right font-medium">Versand</th>
          <th scope="col" className="py-3 text-right font-medium">Kostenlos ab</th>
        </tr>
      </thead>
      <tbody>
        {cart.data.countries.map((country) => (
          <tr key={country.code} className="border-b border-line">
            <th scope="row" className="py-3 pr-4 font-normal">{country.name}</th>
            <td className="py-3 pr-4 text-right tabular-nums">{formatPrice(country.rate_cents)}</td>
            <td className="py-3 text-right tabular-nums">{formatPrice(country.free_from_cents)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
