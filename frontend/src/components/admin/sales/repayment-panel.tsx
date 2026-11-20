"use client";

import { useMutation } from "@tanstack/react-query";
import type { Route } from "next";
import Link from "next/link";
import { useState } from "react";

import { Panel } from "@/components/admin/panel";
import { FormError } from "@/components/forms/form-error";
import { SubmitButton } from "@/components/forms/submit-button";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import {
  getGetRepaymentGirocodeUrl,
  markRepaid,
  setRepaymentAccount,
  useListRepayments,
} from "@/lib/api/generated/admin-sales/admin-sales";
import type { AdminOrderOut, RepaymentOut } from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";
import { formatPrice } from "@/lib/catalog/format";
import { useApiForm } from "@/lib/forms/use-api-form";
import { errorMessage } from "@/lib/i18n/problems";
import { repaymentAccountSchema } from "@/lib/validation/orders";

type RepaymentProps = {
  order: AdminOrderOut & { repayment: RepaymentOut };
  onChanged: (order: AdminOrderOut) => void;
};

/**
 * Money paid by transfer goes back by hand (ADR 0040). The staff type in holder and IBAN from
 * the bank statement; the Stellwerk then shows a GiroCode that the banking app scans, with
 * amount, recipient and reference filled in. Once sent, "Überwiesen" closes it and the IBAN is
 * forgotten.
 */
export function RepaymentPanel({ order, onChanged }: RepaymentProps) {
  const repayment = order.repayment;
  const [editing, setEditing] = useState(repayment.iban === null);

  return (
    <div className="space-y-4 text-small">
      <p className="text-ink-secondary">
        Bezahlt wurde per Überweisung, darum geht das Geld von eurem Konto zurück: auf das Konto, von dem die
        Zahlung kam. Name und IBAN stehen im Kontoauszug bei der Überweisung mit dem Verwendungszweck{" "}
        <span className="font-mono">{order.number}</span>.
      </p>
      <dl className="divide-y divide-line border-y border-line">
        <Row label="Betrag">
          <span className="font-medium tabular-nums">{formatPrice(repayment.amount_cents)}</span>
        </Row>
        <Row label="Verwendungszweck">
          <span className="font-mono">{repayment.reference}</span>
        </Row>
        {repayment.iban !== null && !editing ? (
          <>
            <Row label="Empfänger">{repayment.holder}</Row>
            <Row label="IBAN">
              <span className="font-mono">{repayment.iban}</span>
            </Row>
          </>
        ) : null}
      </dl>

      {editing ? (
        <AccountForm
          order={order}
          onSaved={(updated) => {
            setEditing(false);
            onChanged(updated);
          }}
          onCancel={repayment.iban !== null ? () => setEditing(false) : undefined}
        />
      ) : (
        <>
          <figure className="rounded-md border border-line bg-white p-4">
            {/* eslint-disable-next-line @next/next/no-img-element -- a same-origin SVG, no optimisation wanted */}
            <img
              src={`${getGetRepaymentGirocodeUrl(order.id)}?v=${encodeURIComponent(repayment.iban ?? "")}`}
              alt={`GiroCode: ${formatPrice(repayment.amount_cents)} an ${repayment.holder ?? ""}`}
              width={176}
              height={176}
              className="mx-auto size-44 [image-rendering:pixelated]"
            />
            <figcaption className="mt-3 text-center text-hint text-ink-tertiary">
              In der Banking-App „Scannen“ oder „Foto-Überweisung“ wählen und den Code abfotografieren. Betrag,
              Empfänger und Verwendungszweck sind dann ausgefüllt; ihr gebt nur noch die TAN ein.
            </figcaption>
          </figure>
          <div className="flex flex-wrap items-center gap-3">
            <Repaid order={order} onRepaid={onChanged} />
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="text-small font-medium underline underline-offset-4 hover:text-accent"
            >
              Konto ändern
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-2">
      <dt className="text-ink-tertiary">{label}</dt>
      <dd className="min-w-0 text-right break-words">{children}</dd>
    </div>
  );
}

function AccountForm({
  order,
  onSaved,
  onCancel,
}: {
  order: AdminOrderOut;
  onSaved: (order: AdminOrderOut) => void;
  onCancel?: () => void;
}) {
  const { form, onSubmit, formError } = useApiForm({
    schema: repaymentAccountSchema,
    defaultValues: {
      holder: order.repayment?.holder ?? order.shipping_address.recipient,
      iban: order.repayment?.iban ?? "",
    },
    async submit(values) {
      onSaved(await setRepaymentAccount(order.id, values));
    },
  });
  const {
    register,
    formState: { errors, isSubmitting },
  } = form;

  return (
    <form noValidate onSubmit={onSubmit} aria-label="Konto für die Rückzahlung">
      <FormError message={formError?.message} className="mb-4" />
      <div className="space-y-4">
        <FormField label="Kontoinhaber" hint="Wie im Kontoauszug beim Absender." error={errors.holder?.message}>
          {(control) => <Input {...control} {...register("holder")} maxLength={70} autoComplete="off" />}
        </FormField>
        <FormField label="IBAN" error={errors.iban?.message}>
          {(control) => (
            <Input
              {...control}
              {...register("iban")}
              maxLength={50}
              autoComplete="off"
              spellCheck={false}
              inputMode="text"
              className="font-mono uppercase"
              placeholder="DE00 0000 0000 0000 0000 00"
            />
          )}
        </FormField>
      </div>
      <div className="mt-5 flex flex-wrap items-center gap-3">
        <SubmitButton pending={isSubmitting} pendingLabel="Wird gespeichert …">
          QR-Code zeigen
        </SubmitButton>
        {onCancel ? (
          <Button type="button" variant="secondary" onClick={onCancel}>
            Abbrechen
          </Button>
        ) : null}
      </div>
    </form>
  );
}

function Repaid({ order, onRepaid }: { order: AdminOrderOut & { repayment: RepaymentOut }; onRepaid: (o: AdminOrderOut) => void }) {
  const [open, setOpen] = useState(false);
  const done = useMutation<AdminOrderOut, ApiProblem>({
    mutationFn: () => markRepaid(order.id),
    onSuccess(updated) {
      setOpen(false);
      onRepaid(updated);
    },
  });
  const amount = formatPrice(order.repayment.amount_cents);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          done.reset();
        }
      }}
    >
      <DialogTrigger asChild>
        <Button type="button" size="sm">
          Überwiesen
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogTitle>{amount} zurücküberwiesen?</DialogTitle>
        <DialogDescription>
          Erst antippen, wenn die Überweisung in der Banking-App freigegeben ist. Die Rückzahlung ist dann erledigt,
          und der Shop vergisst die IBAN wieder.
        </DialogDescription>
        <FormError message={done.isError ? errorMessage(done.error) : undefined} className="mt-4" />
        <div className="mt-6 flex flex-wrap justify-end gap-3">
          <DialogClose asChild>
            <Button type="button" variant="secondary">
              Noch nicht
            </Button>
          </DialogClose>
          <Button
            type="button"
            onClick={() => done.mutate()}
            disabled={done.isPending}
            aria-busy={done.isPending || undefined}
          >
            {done.isPending ? "Wird vermerkt …" : "Ja, ist überwiesen"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** The order has a repayment open: narrows the type for the panel. */
export function hasRepayment(order: AdminOrderOut): order is AdminOrderOut & { repayment: RepaymentOut } {
  return order.repayment !== null;
}

/**
 * Above the orders: refunds of transfers that still have to go back, oldest first. Shown only
 * when there are any, and only to those who handle money.
 */
export function RepaymentsPanel() {
  const repayments = useListRepayments();
  const items = repayments.data?.items ?? [];
  if (items.length === 0) {
    return null;
  }
  return (
    <Panel title="Rückzahlungen offen" className="mb-8">
      <ul className="divide-y divide-line">
        {items.map((item) => (
          <li key={item.order_id} className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 py-3 text-small">
            <span>
              <Link
                href={`/admin/bestellungen/${item.order_id}` as Route}
                className="font-mono font-medium underline underline-offset-4 hover:text-accent"
              >
                {item.number}
              </Link>{" "}
              · {item.recipient}
            </span>
            <span className="flex items-baseline gap-4">
              <span className="text-ink-secondary">
                {item.has_account ? "QR-Code bereit" : "IBAN fehlt noch"}
              </span>
              <span className="font-medium tabular-nums">{formatPrice(item.amount_cents)}</span>
            </span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}
