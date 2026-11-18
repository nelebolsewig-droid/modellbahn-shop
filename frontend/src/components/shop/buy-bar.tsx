"use client";

import { useEffect, useState, type RefObject } from "react";

import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import type { VariantAvailabilityOut } from "@/lib/api/generated/model";
import { formatPrice } from "@/lib/catalog/format";
import { availabilityFor, availabilityNote, orderableMax } from "@/lib/sales/availability";
import { useCart, useCartChange } from "@/lib/sales/cart";
import { announceCartAdded } from "@/lib/sales/cart-added";

type BuyBarProps = {
  /** The block with quantity and "In den Warenkorb"; the bar shows while it is out of sight. */
  target: RefObject<HTMLElement | null>;
  variantId: string;
  title: string;
  priceCents: number;
  availability?: VariantAvailabilityOut;
};

/** Whether the element is out of the viewport; false until known, so nothing flashes. */
function useOutOfView(target: RefObject<HTMLElement | null>): boolean {
  const [outOfView, setOutOfView] = useState(false);
  useEffect(() => {
    const element = target.current;
    if (!element || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(([entry]) => setOutOfView(entry ? !entry.isIntersecting : false));
    observer.observe(element);
    return () => observer.disconnect();
  }, [target]);
  return outOfView;
}

/**
 * On the phone the photo and the choices fill nearly two screens before the price. This
 * bar keeps price, delivery and "In den Warenkorb" at the bottom edge while the real
 * button is out of sight; it adds one piece of the chosen variant.
 */
export function BuyBar({ target, variantId, title, priceCents, availability }: BuyBarProps) {
  const outOfView = useOutOfView(target);
  const cart = useCart();
  const change = useCartChange();
  const inCart = cart.data?.lines.find((line) => line.variant_id === variantId)?.quantity ?? 0;
  const state = availability ? availabilityFor(availability, inCart + 1) : null;
  const note = availability && state ? availabilityNote(state, availability.free_units, availability) : null;
  const full = availability !== undefined && inCart >= orderableMax(availability);
  const soldOut = state === "unavailable" || full;

  if (!outOfView) return null;

  return (
    <div
      data-buy-bar=""
      className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-canvas px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] motion-safe:animate-bar-in lg:hidden"
    >
      <div className="mx-auto flex max-w-xl items-center justify-between gap-4">
        <div className="min-w-0">
          <p className="text-body-lg font-semibold tabular-nums">{formatPrice(priceCents)}</p>
          {note ? (
            <StatusBadge tone={note.tone} className="text-hint">
              {note.label}
            </StatusBadge>
          ) : null}
        </div>
        <Button
          type="button"
          disabled={change.isPending || cart.isPending || soldOut}
          aria-busy={change.isPending || undefined}
          onClick={() =>
            change.mutate(
              { variantId, quantity: Math.min(99, inCart + 1) },
              {
                onSuccess: () => announceCartAdded({ variantId, title, quantity: 1 }),
              },
            )
          }
        >
          {change.isPending ? "Wird hinzugefügt …" : soldOut ? "Nicht lieferbar" : "In den Warenkorb"}
        </Button>
      </div>
    </div>
  );
}
