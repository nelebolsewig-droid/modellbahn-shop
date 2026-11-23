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
import { startMakingOrder } from "@/lib/api/generated/admin-sales/admin-sales";
import type { AdminOrderOut } from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";
import { formatClock, formatLongDate } from "@/lib/format";
import { errorMessage } from "@/lib/i18n/problems";

/** A paid order with pieces made for the customer („Fertigung nach Bestellung“, ADR 0029). */
export function madeToOrder(order: AdminOrderOut): boolean {
  return order.status === "paid" && (order.lead_time_min_weeks ?? null) !== null;
}

/**
 * „In Fertigung“ at the order desk (ADR 0046): the customer hears once that their model is
 * being made, as with the mail on dispatch. A started print plate does the same by itself.
 */
export function MakingStart({
  order,
  onStarted,
}: {
  order: AdminOrderOut;
  onStarted: (o: AdminOrderOut) => void;
}) {
  const [open, setOpen] = useState(false);
  const start = useMutation<AdminOrderOut, ApiProblem>({
    mutationFn: () => startMakingOrder(order.id),
    onSuccess(updated) {
      setOpen(false);
      onStarted(updated);
    },
  });

  if (order.making_started_at) {
    const since = new Date(order.making_started_at);
    return (
      <div className="flex items-start gap-3 text-small">
        <span aria-hidden="true" className="mt-1.5 size-2.5 shrink-0 rounded-full bg-accent shadow-[0_0_0_4px] shadow-accent-subtle" />
        <p className="text-ink-secondary">
          <span className="font-medium text-ink">In Fertigung</span> seit {formatLongDate(since)},{" "}
          {formatClock(since)} Uhr. Der Kunde hat die E-Mail bekommen.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4 text-small">
      <p className="text-ink-secondary">
        Wird auf Bestellung gefertigt. Fangt ihr an, hier drücken: Der Kunde bekommt einmalig eine E-Mail, dass
        sein Modell jetzt in Fertigung ist.
      </p>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) {
            start.reset();
          }
        }}
      >
        <DialogTrigger asChild>
          <Button type="button" size="sm">
            In Fertigung
          </Button>
        </DialogTrigger>
        <DialogContent>
          <DialogTitle>{order.number} in Fertigung?</DialogTitle>
          <DialogDescription>
            Der Kunde bekommt jetzt eine E-Mail, dass sein Modell gefertigt wird. Das geht nur einmal.
          </DialogDescription>
          <FormError message={start.isError ? errorMessage(start.error) : undefined} className="mt-4" />
          <div className="mt-6 flex flex-wrap justify-end gap-3">
            <DialogClose asChild>
              <Button type="button" variant="secondary">
                Abbrechen
              </Button>
            </DialogClose>
            <Button
              type="button"
              onClick={() => start.mutate()}
              disabled={start.isPending}
              aria-busy={start.isPending || undefined}
            >
              {start.isPending ? "Wird gesendet …" : "Kunde informieren"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
