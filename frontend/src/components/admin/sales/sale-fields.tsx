"use client";

import { useId } from "react";

import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import type { SaleChannel } from "@/lib/api/generated/model";
import { centsToEuroInput, formatPrice, parseEuroToCents } from "@/lib/catalog/format";
import { CHANNEL_LABELS, CHANNEL_SWATCHES, SALE_CHANNELS } from "@/lib/sales/report";
import { cn } from "@/lib/utils";

const LAST_CHANNEL_KEY = "mb.sale-channel";

/** The channel chosen last on this device: at a fair, every sale is "Messe". */
export function lastSaleChannel(): SaleChannel {
  try {
    const stored = window.localStorage.getItem(LAST_CHANNEL_KEY);
    if (stored && (SALE_CHANNELS as readonly string[]).includes(stored)) {
      return stored as SaleChannel;
    }
  } catch {
    // No storage (private mode): the fair is the usual case.
  }
  return "fair";
}

export function rememberSaleChannel(channel: SaleChannel | ""): void {
  if (channel === "") {
    return;
  }
  try {
    window.localStorage.setItem(LAST_CHANNEL_KEY, channel);
  } catch {
    // Only a convenience.
  }
}

export type SaleDraft = { channel: SaleChannel | ""; price: string };

/** A fresh draft: the last channel, the shop price as the price when there is one. */
export function saleDraft(shopPriceCents: number | null | undefined, channel: SaleChannel | "" = lastSaleChannel()): SaleDraft {
  return { channel, price: typeof shopPriceCents === "number" ? centsToEuroInput(shopPriceCents) : "" };
}

/** The draft as the API takes it; `undefined` while the price cannot be read. */
export function saleOf(draft: SaleDraft): { channel: SaleChannel | null; price_cents: number | null } | undefined {
  const price = draft.price.trim();
  const cents = price === "" ? null : parseEuroToCents(price);
  if (price !== "" && cents === null) {
    return undefined;
  }
  return { channel: draft.channel === "" ? null : draft.channel, price_cents: cents };
}

type SaleFieldsProps = {
  value: SaleDraft;
  onChange: (next: SaleDraft) => void;
  /** Today's shop price of one piece, as a hint; null when the pieces differ. */
  shopPriceCents?: number | null | undefined;
  /** "je Stück" when several pieces go at once. */
  perPiece?: boolean;
  /** Show the price error now (after a submit). */
  showErrors?: boolean;
  className?: string;
};

/**
 * Where a piece sold went and what it brought (ADR 0039): four large choices that work
 * with a thumb at a fair stand, and the price, filled with the shop price. Left empty,
 * the sales report counts the shop price and marks it.
 */
export function SaleFields({ value, onChange, shopPriceCents, perPiece = false, showErrors = false, className }: SaleFieldsProps) {
  const name = useId();
  const unreadable = value.price.trim() !== "" && parseEuroToCents(value.price) === null;
  return (
    <div className={cn("space-y-4 border-l-2 border-action bg-canvas py-3 pr-3 pl-4", className)}>
      <fieldset>
        <legend className="text-small font-medium">Wo verkauft?</legend>
        <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {SALE_CHANNELS.map((channel) => (
            <label
              key={channel}
              className={cn(
                "flex min-h-11 cursor-pointer items-center gap-2.5 border border-line-control bg-surface px-3 text-small transition-colors",
                "hover:border-ink has-checked:border-ink has-checked:bg-ink has-checked:text-on-selected has-focus-visible:outline-2 has-focus-visible:outline-focus",
              )}
            >
              <input
                type="radio"
                name={name}
                value={channel}
                checked={value.channel === channel}
                onChange={() => onChange({ ...value, channel })}
                className="sr-only"
              />
              <span aria-hidden="true" className={cn("size-2.5 shrink-0", CHANNEL_SWATCHES[channel])} />
              {CHANNEL_LABELS[channel]}
            </label>
          ))}
        </div>
      </fieldset>
      <FormField
        label={perPiece ? "Preis je Stück (€)" : "Verkaufspreis (€)"}
        hint={
          typeof shopPriceCents !== "number"
            ? "Leer lassen: Dann zählt der Shoppreis."
            : `Shoppreis ${formatPrice(shopPriceCents)}. Leer lassen: Dann zählt der Shoppreis.`
        }
        error={showErrors && unreadable ? "Bitte einen Betrag wie 49,90 eingeben." : undefined}
      >
        {(control) => (
          <Input
            {...control}
            value={value.price}
            onChange={(event) => onChange({ ...value, price: event.target.value })}
            inputMode="decimal"
            autoComplete="off"
            placeholder="z. B. 35,00"
            className="max-w-48 tabular-nums"
          />
        )}
      </FormField>
    </div>
  );
}
