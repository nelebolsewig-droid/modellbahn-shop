"use client";

import { Close, Content, Description, Portal, Root, Title } from "@radix-ui/react-dialog";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

import { Button } from "@/components/ui/button";
import { ResponsivePicture } from "@/components/ui/responsive-picture";
import { formatPrice } from "@/lib/catalog/format";
import { dismissCartAdded, useCartAdded } from "@/lib/sales/cart-added";
import { useCart } from "@/lib/sales/cart";
import { cn } from "@/lib/utils";

/**
 * After "In den Warenkorb": what went in, the subtotal and the way to the checkout,
 * without leaving the page. A panel below the cart on the desktop, a sheet from the
 * bottom on the phone. Not modal: the page stays usable, Escape or a click outside
 * closes it, focus starts on "Zur Kasse".
 */
export function CartAddedPanel() {
  const added = useCartAdded();
  const cart = useCart();
  const pathname = usePathname();
  const checkout = useRef<HTMLAnchorElement>(null);
  const line = cart.data?.lines.find((candidate) => candidate.variant_id === added?.variantId);

  // A new page (cart, checkout, another model) closes it.
  useEffect(() => {
    dismissCartAdded();
  }, [pathname]);

  return (
    <Root
      open={added !== null}
      onOpenChange={(open) => {
        if (!open) dismissCartAdded();
      }}
      modal={false}
    >
      <Portal>
        <Content
          key={added?.serial}
          onOpenAutoFocus={(event) => {
            // Straight to the next step: "Zur Kasse".
            event.preventDefault();
            checkout.current?.focus();
          }}
          onInteractOutside={(event) => {
            // The buy bar on the phone adds again; that is not a click away from the panel.
            if ((event.target as Element | null)?.closest?.("[data-buy-bar]")) event.preventDefault();
          }}
          className={cn(
            "fixed z-50 bg-surface text-ink shadow-overlay",
            "inset-x-0 bottom-0 rounded-t-lg border-t border-line p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))]",
            "sm:inset-x-auto sm:top-[calc(var(--site-header-height)+0.75rem)] sm:right-[max(1rem,calc((100vw-72rem)/2+2rem))] sm:bottom-auto",
            "sm:w-96 sm:rounded-lg sm:border sm:p-6",
            "motion-safe:animate-panel-in",
          )}
        >
          <div className="flex items-start justify-between gap-4">
            <Title className="flex items-center gap-2 text-body font-semibold">
              <svg
                viewBox="0 0 20 20"
                className="size-5 text-success"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                aria-hidden="true"
              >
                <path d="m4.5 10.5 3.5 3.5 7.5-8" />
              </svg>
              Im Warenkorb
            </Title>
            <Close
              aria-label="Schließen"
              className="-mt-1 -mr-1 grid size-9 place-items-center text-ink-tertiary hover:bg-sunken hover:text-ink"
            >
              <svg
                viewBox="0 0 20 20"
                className="size-4"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                aria-hidden="true"
              >
                <path d="m5 5 10 10M15 5 5 15" />
              </svg>
            </Close>
          </div>

          <div className="mt-4 grid grid-cols-[4rem_minmax(0,1fr)] items-center gap-4">
            <span className="relative aspect-square bg-stage p-1">
              {line?.image ? <ResponsivePicture image={line.image} alt="" sizes="64px" variant="thumb" /> : null}
            </span>
            <Description asChild>
              <div className="min-w-0">
                <p className="text-small font-medium break-words">{added?.title}</p>
                <p className="mt-1 text-hint text-ink-tertiary">
                  {added && added.quantity > 1 ? `${added.quantity} Stück dazu · ` : ""}
                  {line ? `${line.quantity} im Warenkorb` : "Wird geladen …"}
                </p>
              </div>
            </Description>
          </div>

          {cart.data ? (
            <p className="mt-5 flex items-baseline justify-between border-t border-line pt-4 text-small">
              <span className="text-ink-secondary">Zwischensumme · {cart.data.item_count} Artikel</span>
              <span className="font-semibold tabular-nums">{formatPrice(cart.data.totals.subtotal_cents)}</span>
            </p>
          ) : null}

          <div className="mt-5 grid gap-2">
            <Button asChild>
              <Link ref={checkout} href="/kasse">
                Zur Kasse
              </Link>
            </Button>
            <div className="grid grid-cols-2 gap-2">
              <Button asChild variant="secondary" size="sm">
                <Link href="/warenkorb">Warenkorb</Link>
              </Button>
              <Close asChild>
                <Button variant="secondary" size="sm">
                  Weiter stöbern
                </Button>
              </Close>
            </div>
          </div>
        </Content>
      </Portal>
    </Root>
  );
}
