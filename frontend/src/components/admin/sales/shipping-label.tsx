"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

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
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import {
  bookShippingLabel,
  cancelShippingLabel,
  getGetShippingLabelDocumentUrl,
  getGetShippingLabelImageUrl,
  getGetShippingLabelQueryKey,
  getShippingLabel,
} from "@/lib/api/generated/admin-sales/admin-sales";
import {
  ShippingProduct,
  type AdminOrderOut,
  type ShippingLabelOut,
  type ShippingSetupOut,
} from "@/lib/api/generated/model";
import { isApiProblem, type ApiProblem } from "@/lib/api/problem";
import { formatClock, formatLongDate } from "@/lib/format";
import { errorMessage } from "@/lib/i18n/problems";

/** The limits of DHL Paket, as the API checks them (LabelIn). */
export const LABEL_WEIGHT_MIN_G = 10;
export const LABEL_WEIGHT_MAX_G = 31_500;

const PRODUCT_NAMES: Readonly<Record<ShippingProduct, string>> = {
  [ShippingProduct.V01PAK]: "DHL Paket",
  [ShippingProduct.V53WPAK]: "DHL Paket International",
};

/** What DHL books for this address: Paket at home, Paket International in the EU. */
export function productFor(order: AdminOrderOut): ShippingProduct {
  return order.shipping_address.country_code === "DE"
    ? ShippingProduct.V01PAK
    : ShippingProduct.V53WPAK;
}

/** "00340434161094042557" → "0034 0434 1610 9404 2557": easier to compare by eye. */
export function groupDigits(number: string): string {
  return number.replace(/(.{4})(?=.)/g, "$1 ");
}

/** The weight typed in grams, or a message why it does not do. */
export function parseWeight(
  text: string,
): { grams: number } | { problem: string } {
  const cleaned = text.trim().replace(/\s|\./g, "");
  if (!/^\d+$/.test(cleaned)) {
    return { problem: "Bitte das Gewicht in ganzen Gramm angeben, z. B. 850." };
  }
  const grams = Number(cleaned);
  if (grams < LABEL_WEIGHT_MIN_G || grams > LABEL_WEIGHT_MAX_G) {
    return { problem: "DHL Paket nimmt 10 g bis 31.500 g (31,5 kg)." };
  }
  return { grams };
}

/** DHL's own words if it refused the label, else null. */
function carrierReasonOf(error: unknown): string | null {
  return isApiProblem(error) && error.code === "carrier_rejected"
    ? error.detail
    : null;
}

/**
 * The order's label in force, or null when there is none (the API answers 404
 * `label_not_found` then, which is no failure here).
 */
export function useActiveLabel(orderId: string, enabled: boolean) {
  return useQuery<ShippingLabelOut | null, ApiProblem>({
    queryKey: getGetShippingLabelQueryKey(orderId),
    async queryFn({ signal }) {
      try {
        return await getShippingLabel(orderId, { signal });
      } catch (error) {
        if (isApiProblem(error) && error.code === "label_not_found") {
          return null;
        }
        throw error;
      }
    },
    enabled,
  });
}

/**
 * The parcel's label at the packing desk (ADR 0023): weigh, book with DHL, print on the
 * 100 × 150 mm label printer. A wrong label is cancelled at DHL and booked anew.
 */
export function ShippingLabelDesk({
  order,
  setup,
  label,
}: {
  order: AdminOrderOut;
  setup: ShippingSetupOut;
  label: ShippingLabelOut | null;
}) {
  return label ? (
    <LabelCard order={order} label={label} />
  ) : (
    <BookLabel order={order} setup={setup} />
  );
}

function BookLabel({
  order,
  setup,
}: {
  order: AdminOrderOut;
  setup: ShippingSetupOut;
}) {
  const queryClient = useQueryClient();
  const [weight, setWeight] = useState(String(setup.default_weight_g));
  const [problem, setProblem] = useState<string | undefined>(undefined);
  const product = productFor(order);
  const book = useMutation<ShippingLabelOut, ApiProblem, number>({
    mutationFn: (grams) => bookShippingLabel(order.id, { weight_g: grams }),
    onSuccess(booked) {
      queryClient.setQueryData(getGetShippingLabelQueryKey(order.id), booked);
    },
  });
  const reason = carrierReasonOf(book.error);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsed = parseWeight(weight);
    if ("problem" in parsed) {
      setProblem(parsed.problem);
      return;
    }
    setProblem(undefined);
    book.mutate(parsed.grams);
  }

  return (
    <form
      noValidate
      onSubmit={submit}
      aria-label={`${setup.carrier}-Label buchen`}
    >
      <p className="flex items-baseline justify-between gap-3">
        <span className="label-caps text-ink-tertiary">Label</span>
        <span className="font-mono text-hint text-ink-secondary">
          {PRODUCT_NAMES[product]}
        </span>
      </p>
      <FormField
        label="Gewicht in Gramm"
        hint="Das gepackte Paket, mit Karton und Füllmaterial."
        error={problem}
        className="mt-3"
      >
        {(control) => (
          <div className="flex items-center gap-3">
            <Input
              {...control}
              value={weight}
              onChange={(event) => setWeight(event.target.value)}
              inputMode="numeric"
              autoComplete="off"
              maxLength={6}
              className="max-w-36 font-mono tabular-nums"
            />
            <span className="text-small text-ink-secondary">g</span>
          </div>
        )}
      </FormField>
      <FormError
        message={book.isError ? errorMessage(book.error) : undefined}
        className="mt-4"
      />
      {reason ? (
        <CarrierReason carrier={setup.carrier} reason={reason} />
      ) : null}
      <Button
        type="submit"
        size="sm"
        className="mt-4 w-full"
        disabled={book.isPending}
        aria-busy={book.isPending || undefined}
      >
        {book.isPending
          ? `${setup.carrier} bucht …`
          : `${setup.carrier}-Label buchen`}
      </Button>
    </form>
  );
}

function LabelCard({
  order,
  label,
}: {
  order: AdminOrderOut;
  label: ShippingLabelOut;
}) {
  const url = getGetShippingLabelDocumentUrl(order.id);
  const booked = new Date(label.created_at);
  return (
    <div>
      <figure className="rounded-md border border-line-control bg-surface p-4">
        <figcaption className="flex items-baseline justify-between gap-3">
          <span className="label-caps text-ink-tertiary">
            {label.carrier}-Label
          </span>
          <span className="font-mono text-hint text-ink-secondary">
            {PRODUCT_NAMES[label.product]}
          </span>
        </figcaption>
        <p
          className="mt-3 font-mono text-body font-medium tabular-nums break-all"
          aria-label="Sendungsnummer"
        >
          {groupDigits(label.shipment_number)}
        </p>
        <p className="mt-2 text-hint text-ink-tertiary tabular-nums">
          {formatWeight(label.weight_g)} · gebucht {formatLongDate(booked)},{" "}
          {formatClock(booked)} Uhr
        </p>
      </figure>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button asChild size="sm">
          <a href={url} target="_blank" rel="noopener">
            Label drucken
          </a>
        </Button>
        <Button asChild size="sm" variant="secondary">
          <a
            href={url}
            download={`${label.carrier}-${label.shipment_number}.pdf`}
          >
            Herunterladen
          </a>
        </Button>
        <Button asChild size="sm" variant="secondary">
          <a
            href={getGetShippingLabelImageUrl(order.id)}
            download={`${label.carrier}-${label.shipment_number}.png`}
          >
            Als Bild
          </a>
        </Button>
      </div>
      <p className="mt-3 text-hint text-ink-tertiary">
        Im Druckdialog den Etikettendrucker wählen, Papier{" "}
        <span className="whitespace-nowrap">100 × 150 mm</span>, „Tatsächliche
        Größe“. Druckt die App des Druckers nur Bilder (etwa Brother), „Als
        Bild“ nehmen.
      </p>
      {order.status === "paid" ? (
        <CancelLabel order={order} label={label} />
      ) : null}
    </div>
  );
}

function CancelLabel({
  order,
  label,
}: {
  order: AdminOrderOut;
  label: ShippingLabelOut;
}) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const cancel = useMutation<void, ApiProblem>({
    mutationFn: () => cancelShippingLabel(order.id),
    onSuccess() {
      setOpen(false);
      queryClient.setQueryData(getGetShippingLabelQueryKey(order.id), null);
    },
  });
  const reason = carrierReasonOf(cancel.error);
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          cancel.reset();
        }
      }}
    >
      <DialogTrigger asChild>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="mt-2 -ml-5 werkstatt:-ml-4"
        >
          Label stornieren
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogTitle>{label.carrier}-Label stornieren?</DialogTitle>
        <DialogDescription>
          {label.carrier} streicht die Sendung{" "}
          <span className="font-mono font-medium whitespace-nowrap text-ink">
            {groupDigits(label.shipment_number)}
          </span>
          ; das gedruckte Label gilt dann nicht mehr. Danach lässt sich ein
          neues buchen, etwa mit dem richtigen Gewicht.
        </DialogDescription>
        <FormError
          message={cancel.isError ? errorMessage(cancel.error) : undefined}
          className="mt-4"
        />
        {reason ? (
          <CarrierReason carrier={label.carrier} reason={reason} />
        ) : null}
        <div className="mt-6 flex flex-wrap justify-end gap-3">
          <DialogClose asChild>
            <Button type="button" variant="secondary">
              Behalten
            </Button>
          </DialogClose>
          <Button
            type="button"
            variant="danger"
            onClick={() => cancel.mutate()}
            disabled={cancel.isPending}
            aria-busy={cancel.isPending || undefined}
          >
            {cancel.isPending ? "Wird storniert …" : "Label stornieren"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** A shipped order's label, to print it once more. */
export function LabelReprint({
  order,
  label,
}: {
  order: AdminOrderOut;
  label: ShippingLabelOut;
}) {
  return (
    <a
      href={getGetShippingLabelDocumentUrl(order.id)}
      target="_blank"
      rel="noopener"
      className="text-small text-accent hover:underline hover:underline-offset-4"
    >
      {label.carrier}-Label öffnen
    </a>
  );
}

function CarrierReason({
  carrier,
  reason,
}: {
  carrier: string;
  reason: string;
}) {
  return (
    <p className="mt-2 text-hint text-ink-secondary">
      {carrier} sagt: <span className="font-mono break-words">{reason}</span>
    </p>
  );
}

function formatWeight(grams: number): string {
  return grams >= 1000
    ? `${(grams / 1000).toLocaleString("de-DE", { maximumFractionDigits: 3 })} kg`
    : `${grams} g`;
}
