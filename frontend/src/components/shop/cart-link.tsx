"use client";

import Link from "next/link";

import { useCart } from "@/lib/sales/cart";
import { cn } from "@/lib/utils";

/** The cart in the header: an outlined wagon with the number of pieces in it. */
export function CartLink() {
  const cart = useCart();
  const count = cart.data?.item_count ?? 0;
  const label = count === 0 ? "Warenkorb, leer" : `Warenkorb, ${count} Artikel`;

  return (
    <Link
      href="/warenkorb"
      aria-label={label}
      className="relative grid size-10 place-items-center rounded-full text-ink-secondary hover:bg-sunken hover:text-ink"
    >
      {/* A goods wagon in side view, drawn like the blueprint lines of the shop. */}
      <svg viewBox="0 0 24 24" className="size-6" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true">
        <path d="M3 7.5h18v8H3z" />
        <path d="M7 7.5v8M12 7.5v8M17 7.5v8" />
        <path d="M2 15.5h20" />
        <circle cx="7" cy="18" r="1.6" />
        <circle cx="17" cy="18" r="1.6" />
      </svg>
      <span
        aria-hidden="true"
        className={cn(
          "absolute -top-0.5 -right-0.5 grid h-5 min-w-5 place-items-center rounded-full bg-selected px-1",
          "text-[0.6875rem] leading-none font-semibold text-on-selected tabular-nums transition-transform duration-150",
          count === 0 && "scale-0",
        )}
      >
        {count > 99 ? "99+" : count}
      </span>
    </Link>
  );
}
