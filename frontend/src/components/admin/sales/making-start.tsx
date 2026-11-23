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
import { startFinishingOrder, startMakingOrder } from "@/lib/api/generated/admin-sales/admin-sales";
import type { AdminOrderOut } from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";
import { formatClock, formatLongDate } from "@/lib/format";
import { errorMessage } from "@/lib/i18n/problems";
import { cn } from "@/lib/utils";

/** A paid order with pieces made for the customer („Fertigung nach Bestellung“, ADR 0029). */
export function madeToOrder(order: AdminOrderOut): boolean {
  return order.status === "paid" && (order.lead_time_min_weeks ?? null) !== null;
}

type Step = {
  label: string;
  done: string | null | undefined;
  mail: string;
  send: (id: string) => Promise<AdminOrderOut>;
};

/**
 * The workshop steps at the order desk (ADR 0046): „Im Druck“ and „Lackierung & Montage“.
 * Each tells the customer once by e-mail, like the mail on dispatch. A started print plate
 * marks „Im Druck“ by itself.
 */
export function MakingStart({ order, onStarted }: { order: AdminOrderOut; onStarted: (o: AdminOrderOut) => void }) {
  const steps: Step[] = [
    { label: "Im Druck", done: order.making_started_at, mail: "sein Modell jetzt gedruckt wird", send: startMakingOrder },
    {
      label: "Lackierung & Montage",
      done: order.finishing_started_at,
      mail: "sein Modell jetzt lackiert und montiert wird",
      send: startFinishingOrder,
    },
  ];
  return (
    <div className="space-y-4 text-small">
      <p className="text-ink-secondary">
        Wird auf Bestellung gefertigt. Bei jedem Schritt bekommt der Kunde einmalig eine E-Mail.
      </p>
      <ol className="space-y-2">
        {steps.map((step, index) => (
          <StepRow key={step.label} step={step} index={index + 1} order={order} onStarted={onStarted} />
        ))}
      </ol>
    </div>
  );
}

function StepRow({
  step,
  index,
  order,
  onStarted,
}: {
  step: Step;
  index: number;
  order: AdminOrderOut;
  onStarted: (o: AdminOrderOut) => void;
}) {
  const [open, setOpen] = useState(false);
  const start = useMutation<AdminOrderOut, ApiProblem>({
    mutationFn: () => step.send(order.id),
    onSuccess(updated) {
      setOpen(false);
      onStarted(updated);
    },
  });
  const since = step.done ? new Date(step.done) : null;

  return (
    <li
      className={cn(
        "flex items-center gap-3 rounded-md border px-3 py-2.5",
        since ? "border-line bg-canvas" : "border-line-strong bg-surface shadow-sm",
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "grid size-6 shrink-0 place-items-center rounded-full font-mono text-hint",
          since ? "bg-accent text-on-accent" : "border border-line-strong text-ink-tertiary",
        )}
      >
        {since ? "✓" : index}
      </span>
      <div className="min-w-0 flex-1">
        <p className="font-medium">{step.label}</p>
        {since ? (
          <p className="text-hint text-ink-tertiary">
            seit {formatLongDate(since)}, {formatClock(since)} Uhr · Mail verschickt
          </p>
        ) : null}
      </div>
      {since ? null : (
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
              {step.label}
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogTitle>
              {order.number}: {step.label}?
            </DialogTitle>
            <DialogDescription>
              Der Kunde bekommt jetzt eine E-Mail, dass {step.mail}. Das geht nur einmal.
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
      )}
    </li>
  );
}
