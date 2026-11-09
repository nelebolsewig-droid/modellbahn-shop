"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { RefundRefusal, refusalOf } from "@/components/admin/sales/refund-refusal";
import { FormError } from "@/components/forms/form-error";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { refundOrder } from "@/lib/api/generated/admin-sales/admin-sales";
import type { AdminOrderOut } from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";
import { formatPrice } from "@/lib/catalog/format";
import { errorMessage } from "@/lib/i18n/problems";
import { cn } from "@/lib/utils";

type Mode = "whole" | "lines";

/** What can still go back: the rest of the captured payment. */
export function refundableCents(order: AdminOrderOut): number {
  const payment = order.payments.find((p) => p.status === "captured");
  return payment ? payment.amount_cents - payment.refunded_cents : 0;
}

/**
 * Refund after a return (ADR 0020): the whole order or the articles that came back. SumUp pays
 * back at once and the customer gets an e-mail. A whole order that has not been shipped is
 * cancelled instead; that happens by itself when the customer withdraws.
 */
export function RefundPanel({ order, onRefunded }: { order: AdminOrderOut; onRefunded: (o: AdminOrderOut) => void }) {
  const shipped = order.status === "shipped";
  const refundable = refundableCents(order);
  const refunded = order.payments.reduce((sum, p) => sum + p.refunded_cents, 0);
  const [mode, setMode] = useState<Mode>(shipped ? "whole" : "lines");
  const [lines, setLines] = useState<ReadonlySet<number>>(new Set());
  const [open, setOpen] = useState(false);
  const linesCents = order.lines.reduce((sum, line, index) => sum + (lines.has(index) ? line.line_total_cents : 0), 0);
  const amount = Math.min(mode === "whole" ? refundable : linesCents, refundable);
  const refund = useMutation<AdminOrderOut, ApiProblem, { cents: number; byHand: boolean }>({
    mutationFn: ({ cents, byHand }) =>
      refundOrder(order.id, { amount_cents: cents, refunded_by_hand: byHand }),
    onSuccess(updated) {
      setOpen(false);
      setLines(new Set());
      onRefunded(updated);
    },
  });

  // SumUp's answer when it refused; the staff may then refund in SumUp and only record it.
  const refusal = refusalOf(refund.error);

  if (refundable === 0) {
    return (
      <p className="text-small text-ink-secondary">
        {refunded > 0
          ? `Erstattet: ${formatPrice(refunded)}. Es ist nichts mehr offen.`
          : "Es gibt nichts zu erstatten."}
      </p>
    );
  }

  const toggle = (index: number) =>
    setLines((current) => {
      const next = new Set(current);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });

  return (
    <div className="space-y-4 text-small">
      <p className="text-ink-secondary">
        {shipped
          ? "Ist die Ware zurück (oder hat der Kunde die Rücksendung nachgewiesen), hier erstatten. SumUp zahlt sofort zurück, der Kunde bekommt eine E-Mail."
          : "Einzelne Artikel erstatten, die nicht verschickt werden. Für die ganze Bestellung: stornieren."}
        {refunded > 0 ? ` Schon erstattet: ${formatPrice(refunded)}.` : ""}
      </p>
      {shipped ? (
        <div role="radiogroup" aria-label="Was wird erstattet?" className="flex flex-wrap gap-2">
          {(
            [
              ["whole", `Alles Offene (${formatPrice(refundable)})`],
              ["lines", "Einzelne Artikel"],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={mode === value}
              onClick={() => setMode(value)}
              className={cn(
                "rounded-full border px-4 py-1.5 font-medium transition-colors",
                mode === value
                  ? "border-selected bg-selected text-on-selected"
                  : "border-line-control text-ink hover:border-ink",
              )}
            >
              {label}
            </button>
          ))}
        </div>
      ) : null}
      {mode === "lines" ? (
        <fieldset>
          <legend className="sr-only">Artikel, die zurückgekommen sind</legend>
          <ul className="space-y-2">
            {order.lines.map((line, index) => (
              <li key={`${line.sku}-${index}`}>
                <label className="flex items-start gap-3">
                  <input
                    type="checkbox"
                    checked={lines.has(index)}
                    onChange={() => toggle(index)}
                    className="mt-1 size-4 shrink-0 accent-[var(--selected)]"
                  />
                  <span className="min-w-0 flex-1">
                    {line.quantity} × {line.title}
                  </span>
                  <span className="tabular-nums">{formatPrice(line.line_total_cents)}</span>
                </label>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-hint text-ink-tertiary">Versandkosten gehen nur bei der ganzen Bestellung zurück.</p>
        </fieldset>
      ) : null}
      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) {
            refund.reset();
          }
        }}
      >
        <DialogTrigger asChild>
          <Button type="button" size="sm" disabled={amount === 0}>
            {shipped ? "Rücksendung erhalten – " : ""}
            {formatPrice(amount)} erstatten
          </Button>
        </DialogTrigger>
        <DialogContent>
          <DialogTitle>{formatPrice(amount)} erstatten?</DialogTitle>
          <DialogDescription>
            SumUp zahlt {formatPrice(amount)} für {order.number} auf das Zahlungsmittel des Kunden zurück. Das lässt
            sich nicht rückgängig machen.
          </DialogDescription>
          <FormError message={refund.isError ? errorMessage(refund.error) : undefined} className="mt-4" />
          {refusal ? <RefundRefusal reason={refusal} /> : null}
          <div className="mt-6 flex flex-wrap justify-end gap-3">
            <DialogClose asChild>
              <Button type="button" variant="secondary">
                Abbrechen
              </Button>
            </DialogClose>
            {refusal ? (
              <Button
                type="button"
                variant="secondary"
                onClick={() => refund.mutate({ cents: amount, byHand: true })}
                disabled={refund.isPending}
              >
                Im SumUp-Konto erstattet, nur vermerken
              </Button>
            ) : null}
            <Button
              type="button"
              onClick={() => refund.mutate({ cents: amount, byHand: false })}
              disabled={refund.isPending}
              aria-busy={refund.isPending || undefined}
            >
              {refund.isPending ? "Wird erstattet …" : "Erstatten"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
