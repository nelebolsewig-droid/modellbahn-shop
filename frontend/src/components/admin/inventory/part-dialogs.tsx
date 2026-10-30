"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { countParts, useListLocations, writeOffReceipt } from "@/lib/api/generated/admin-inventory/admin-inventory";
import type { PartDetailsOut, ReceiptOut, StockPartOut } from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";
import { partCount } from "@/lib/inventory/labels";
import { errorMessage } from "@/lib/i18n/problems";

import { LabelPrinter } from "./label-printer";

const INVENTORY_PREFIX = "/api/v1/admin/inventory/";

/** After a booking: every stock view loads again (boxes, receiving, the part, the tree). */
export function useInventoryRefresh() {
  const queryClient = useQueryClient();
  return () =>
    void queryClient.invalidateQueries({
      predicate: (query) => String(query.queryKey[0]).startsWith(INVENTORY_PREFIX),
    });
}

function Failure({ error }: { error: unknown }) {
  return (
    <p role="alert" className="text-small text-danger not-empty:mt-4">
      {error ? errorMessage(error) : null}
    </p>
  );
}

type CountPartsDialogProps = {
  part: StockPartOut;
  /** Counting one box: its code is fixed. Otherwise any place that holds goods. */
  locationCode?: string;
  current?: number;
  trigger: ReactNode;
};

/**
 * "Gezählt": the quantity in a box is set to what was counted there; the journal books
 * the difference. Also how parts that were never printed here get into the store.
 */
export function CountPartsDialog({ part, locationCode, current, trigger }: CountPartsDialogProps) {
  const [open, setOpen] = useState(false);
  const [place, setPlace] = useState(locationCode ?? "");
  const [quantity, setQuantity] = useState(current === undefined ? "" : String(current));
  const [note, setNote] = useState("");
  const refresh = useInventoryRefresh();
  const places = useListLocations({
    query: {
      enabled: open && locationCode === undefined,
      select: (tree) => tree.items.filter((item) => item.holds_goods),
    },
  });
  const counted = Number.parseInt(quantity, 10);
  const valid = place !== "" && Number.isInteger(counted) && counted >= 0 && /^\d+$/.test(quantity.trim());
  const save = useMutation<PartDetailsOut, ApiProblem>({
    mutationFn: () => countParts(part.part_number, { location_code: place, quantity: counted, note }),
    onSuccess() {
      refresh();
      setOpen(false);
    },
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          setPlace(locationCode ?? "");
          setQuantity(current === undefined ? "" : String(current));
          setNote("");
          save.reset();
        }
      }}
    >
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogTitle>{locationCode ? `${locationCode} gezählt` : "Teile gezählt"}</DialogTitle>
        <DialogDescription>
          {part.name} · <span className="font-mono">{part.part_number}</span>. Trag ein, wie viele dort liegen; das
          Journal bucht den Unterschied.
        </DialogDescription>
        <form
          noValidate
          className="mt-6 space-y-5"
          onSubmit={(event) => {
            event.preventDefault();
            if (valid) {
              save.mutate();
            }
          }}
        >
          {locationCode === undefined ? (
            <FormField label="Platz">
              {(control) => (
                <Select
                  {...control}
                  value={place}
                  onChange={(event) => setPlace(event.target.value)}
                  disabled={places.isPending}
                >
                  <option value="">Box oder Fach wählen</option>
                  {(places.data ?? []).map((location) => (
                    <option key={location.id} value={location.code}>
                      {location.code}
                      {location.name ? ` · ${location.name}` : ""}
                    </option>
                  ))}
                </Select>
              )}
            </FormField>
          ) : null}
          <FormField label="Gezählt" hint={current === undefined ? undefined : `Bisher gebucht: ${partCount(current)}`}>
            {(control) => (
              <Input
                {...control}
                value={quantity}
                onChange={(event) => setQuantity(event.target.value)}
                type="number"
                inputMode="numeric"
                min={0}
              />
            )}
          </FormField>
          <FormField label="Hinweis" hint="Optional, z. B. „Altbestand“ oder „zwei zerbrochen“">
            {(control) => (
              <Textarea {...control} value={note} onChange={(event) => setNote(event.target.value)} rows={2} />
            )}
          </FormField>
          <Failure error={save.error} />
          <div className="flex flex-wrap justify-end gap-3">
            <Button type="button" variant="secondary" size="sm" onClick={() => setOpen(false)}>
              Abbrechen
            </Button>
            <Button type="submit" size="sm" disabled={!valid || save.isPending} aria-busy={save.isPending || undefined}>
              {save.isPending ? "Wird gebucht …" : "Bestand setzen"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** The rest of a receipt never reached a shelf: lost or broken on the way. */
export function WriteOffDialog({ receipt, trigger }: { receipt: ReceiptOut; trigger: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const refresh = useInventoryRefresh();
  const save = useMutation<ReceiptOut, ApiProblem>({
    mutationFn: () => writeOffReceipt(receipt.id, { note }),
    onSuccess() {
      refresh();
      setOpen(false);
    },
  });
  const what = receipt.part?.name ?? "Teile";
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          setNote("");
          save.reset();
        }
      }}
    >
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogTitle>
          {receipt.open} × {what} ausbuchen
        </DialogTitle>
        <DialogDescription>
          {receipt.print_job ? `Aus Druck ${receipt.print_job.number}. ` : ""}Sie kommen nie in eine Box: verloren oder
          auf dem Weg zerbrochen. Das Journal behält es.
        </DialogDescription>
        <div className="mt-6">
          <FormField label="Grund" hint="Optional">
            {(control) => (
              <Textarea
                {...control}
                value={note}
                onChange={(event) => setNote(event.target.value)}
                rows={2}
                placeholder="beim Waschen zerbrochen"
              />
            )}
          </FormField>
        </div>
        <Failure error={save.error} />
        <div className="mt-6 flex flex-wrap justify-end gap-3">
          <Button type="button" variant="secondary" size="sm" onClick={() => setOpen(false)}>
            Abbrechen
          </Button>
          <Button
            type="button"
            size="sm"
            variant="danger"
            disabled={save.isPending}
            aria-busy={save.isPending || undefined}
            onClick={() => save.mutate()}
          >
            {save.isPending ? "Wird ausgebucht …" : "Ausbuchen"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** The label for the box a part lies in: its number as Code 128. */
export function PartLabelDialog({ part, trigger }: { part: StockPartOut; trigger: ReactNode }) {
  return (
    <Dialog>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogTitle>Etikett für {part.name}</DialogTitle>
        <DialogDescription>
          Kommt auf die Box, in der die Teile liegen. Beim Einlagern erst den Platz scannen, dann dieses Etikett.
        </DialogDescription>
        <LabelPrinter partNumbers={[part.part_number]} className="mt-6" />
      </DialogContent>
    </Dialog>
  );
}
