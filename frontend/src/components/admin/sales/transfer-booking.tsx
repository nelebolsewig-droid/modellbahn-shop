"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

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
import { confirmBankTransfer } from "@/lib/api/generated/admin-sales/admin-sales";
import type { AdminOrderOut, PaymentOut } from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";
import { formatPrice } from "@/lib/catalog/format";
import { formatClock, formatLongDate } from "@/lib/format";
import { errorMessage } from "@/lib/i18n/problems";
import { BANK_TRANSFER } from "@/lib/sales/labels";

/** The bank transfer the order waits for, if it waits for one (ADR 0022). */
export function awaitedTransfer(order: AdminOrderOut): PaymentOut | undefined {
  return order.payments.find(
    (payment) =>
      payment.status === "pending" && payment.provider === BANK_TRANSFER,
  );
}

/** Paid by bank transfer: what goes back, goes back by hand. */
export function paidByTransfer(order: AdminOrderOut): boolean {
  return order.payments.some(
    (payment) =>
      payment.provider === BANK_TRANSFER &&
      (payment.status === "captured" || payment.status === "refunded"),
  );
}

/**
 * Payment in advance at the order desk: what to look for in the account statement, and the
 * button that books the money once it is there. The customer then gets the usual mail.
 */
export function TransferBooking({
  order,
  onBooked,
}: {
  order: AdminOrderOut;
  onBooked: (o: AdminOrderOut) => void;
}) {
  const [open, setOpen] = useState(false);
  const book = useMutation<AdminOrderOut, ApiProblem>({
    mutationFn: () => confirmBankTransfer(order.id),
    onSuccess(updated) {
      setOpen(false);
      onBooked(updated);
    },
  });
  const due = order.payment_due_at ? new Date(order.payment_due_at) : null;
  const amount = formatPrice(order.totals.total_cents);

  return (
    <div className="space-y-4 text-small">
      <p className="text-ink-secondary">
        Der Kunde zahlt per Vorkasse. Kommt im Kontoauszug eine Überweisung mit
        diesem Verwendungszweck an, hier buchen; dann geht die Bestellung in die
        Kommissionierung.
      </p>
      <dl className="divide-y divide-line border-y border-line">
        <div className="flex justify-between gap-4 py-2">
          <dt className="text-ink-tertiary">Verwendungszweck</dt>
          <dd className="font-mono font-medium">{order.number}</dd>
        </div>
        <div className="flex justify-between gap-4 py-2">
          <dt className="text-ink-tertiary">Betrag</dt>
          <dd className="font-medium tabular-nums">{amount}</dd>
        </div>
        {due ? (
          <div className="flex justify-between gap-4 py-2">
            <dt className="text-ink-tertiary">Frist</dt>
            <dd className="tabular-nums">
              {formatLongDate(due)}, {formatClock(due)} Uhr
            </dd>
          </div>
        ) : null}
      </dl>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) {
            book.reset();
          }
        }}
      >
        <DialogTrigger asChild>
          <Button type="button" size="sm">
            Überweisung eingegangen
          </Button>
        </DialogTrigger>
        <DialogContent>
          <DialogTitle>
            {amount} für {order.number} eingegangen?
          </DialogTitle>
          <DialogDescription>
            Bucht die Zahlung: Die Bestellung ist dann bezahlt und verbindlich,
            der Kunde bekommt die Bestätigung per E-Mail. Prüft vorher Betrag
            und Verwendungszweck im Kontoauszug.
          </DialogDescription>
          <FormError
            message={book.isError ? errorMessage(book.error) : undefined}
            className="mt-4"
          />
          <div className="mt-6 flex flex-wrap justify-end gap-3">
            <DialogClose asChild>
              <Button type="button" variant="secondary">
                Abbrechen
              </Button>
            </DialogClose>
            <Button
              type="button"
              onClick={() => book.mutate()}
              disabled={book.isPending}
              aria-busy={book.isPending || undefined}
            >
              {book.isPending ? "Wird gebucht …" : "Zahlung buchen"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
