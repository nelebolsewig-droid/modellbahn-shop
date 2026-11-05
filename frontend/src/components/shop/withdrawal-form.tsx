"use client";

import { useState } from "react";

import { FormError } from "@/components/forms/form-error";
import { ResultPanel } from "@/components/forms/result-panel";
import { SubmitButton } from "@/components/forms/submit-button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type { WithdrawalReceiptOut } from "@/lib/api/generated/model";
import { withdrawContract } from "@/lib/api/generated/store-sales/store-sales";
import { useApiForm } from "@/lib/forms/use-api-form";
import { formatClock, formatLongDate } from "@/lib/format";
import { withdrawalSchema } from "@/lib/validation/withdrawal";

/**
 * The withdrawal function (§ 356a BGB): name, contract and an address for the
 * confirmation, then "Widerruf bestätigen". The answer is the same whether or not the
 * number fits an order; the receipt repeats what came in and when, as the e-mail does.
 */
export function WithdrawalForm({ orderNumber = "" }: { orderNumber?: string }) {
  const [receipt, setReceipt] = useState<WithdrawalReceiptOut | null>(null);
  const { form, onSubmit, formError } = useApiForm({
    schema: withdrawalSchema,
    defaultValues: { name: "", order_number: orderNumber, email: "", scope: "" },
    async submit(values) {
      setReceipt(await withdrawContract({ ...values, scope: values.scope.trim() }));
    },
  });
  const {
    register,
    formState: { errors, isSubmitting },
  } = form;

  if (receipt !== null) {
    const received = new Date(receipt.received_at);
    return (
      <ResultPanel tone="success" title="Dein Widerruf ist eingegangen">
        <p>
          Eingegangen am {formatLongDate(received)} um {formatClock(received)} Uhr. Die Bestätigung mit diesen Angaben
          ist unterwegs an <strong className="break-all">{receipt.email}</strong>.
        </p>
        <dl className="mt-4 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1.5">
          <dt className="text-ink-tertiary">Name</dt>
          <dd>{receipt.name}</dd>
          <dt className="text-ink-tertiary">Bestellung</dt>
          <dd className="font-mono">{receipt.order_number}</dd>
          <dt className="text-ink-tertiary">Widerrufen</dt>
          <dd>{receipt.scope || "die ganze Bestellung"}</dd>
        </dl>
        <p className="mt-4">
          Ist die Ware schon bei dir, schick sie bitte innerhalb von 14 Tagen zurück; die Anschrift steht in der E-Mail.
          Den Betrag erstatten wir dir auf dem Weg, auf dem du bezahlt hast.
        </p>
      </ResultPanel>
    );
  }

  return (
    <form noValidate onSubmit={onSubmit} aria-label="Vertrag widerrufen">
      <FormError message={formError?.message} />
      <div className="space-y-5">
        <FormField label="Dein Name" error={errors.name?.message}>
          {(control) => <Input {...control} {...register("name")} autoComplete="name" />}
        </FormField>
        <FormField
          label="Bestellnummer"
          hint="Sie steht in der Bestätigung deiner Bestellung, z. B. MB-2026-00042."
          error={errors.order_number?.message}
        >
          {(control) => (
            <Input
              {...control}
              {...register("order_number")}
              autoCapitalize="characters"
              spellCheck={false}
              className="font-mono"
            />
          )}
        </FormField>
        <FormField
          label="E-Mail-Adresse"
          hint="Dorthin schicken wir dir sofort die Eingangsbestätigung."
          error={errors.email?.message}
        >
          {(control) => (
            <Input
              {...control}
              {...register("email")}
              type="email"
              inputMode="email"
              autoComplete="email"
              autoCapitalize="none"
              spellCheck={false}
            />
          )}
        </FormField>
        <FormField
          label="Nur einzelne Artikel widerrufen? (freiwillig)"
          hint="Nenn sie hier. Bleibt das Feld leer, gilt der Widerruf für die ganze Bestellung."
          error={errors.scope?.message}
        >
          {(control) => <Textarea {...control} {...register("scope")} rows={3} />}
        </FormField>
        <div className="border-t border-line pt-5">
          <p className="text-hint text-ink-tertiary">
            Mit „Widerruf bestätigen“ widerrufst du den Vertrag. Der Widerruf gilt mit dem Eingang bei uns.
          </p>
          <SubmitButton pending={isSubmitting} pendingLabel="Wird gesendet …" className="mt-4 w-full">
            Widerruf bestätigen
          </SubmitButton>
        </div>
      </div>
    </form>
  );
}
