"use client";

import Link from "next/link";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { QuantityStepper } from "@/components/ui/quantity-stepper";
import { errorMessage } from "@/lib/i18n/problems";
import { useCart, useCartChange } from "@/lib/sales/cart";

type AddToCartProps = {
  variantId: string;
  /** "Stellwerk Altenau · H0 · bemalt", for the confirmation. */
  title: string;
};

/**
 * Quantity and "In den Warenkorb". Adding counts on top of what is already in the
 * cart; the confirmation stays until the selection changes (the parent remounts it).
 */
export function AddToCart({ variantId, title }: AddToCartProps) {
  const [quantity, setQuantity] = useState(1);
  const cart = useCart();
  const change = useCartChange();
  const inCart = cart.data?.lines.find((line) => line.variant_id === variantId)?.quantity ?? 0;

  const add = () => {
    change.mutate({ variantId, quantity: Math.min(99, inCart + quantity) });
  };

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <QuantityStepper value={quantity} onChange={setQuantity} label="Menge" disabled={change.isPending} />
        <Button
          type="button"
          onClick={add}
          disabled={change.isPending || cart.isPending}
          aria-busy={change.isPending || undefined}
          className="min-w-52"
        >
          {change.isPending ? "Wird hinzugefügt …" : "In den Warenkorb"}
        </Button>
      </div>
      <div role="status" className="not-empty:mt-4">
        {change.isSuccess ? (
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-small">
            <span className="inline-flex items-center gap-2 font-medium text-success">
              <svg viewBox="0 0 20 20" className="size-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <path d="m4.5 10.5 3.5 3.5 7.5-8" />
              </svg>
              Im Warenkorb: {title}
            </span>
            <Link href="/warenkorb" className="font-medium text-accent underline-offset-4 hover:underline">
              Zum Warenkorb ({change.data.item_count})
            </Link>
          </p>
        ) : null}
      </div>
      {change.isError ? (
        <Alert tone="danger" title="Das hat nicht geklappt" className="mt-4">
          <p>{errorMessage(change.error)}</p>
        </Alert>
      ) : null}
    </div>
  );
}
