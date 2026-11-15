"use client";

import { useMutation } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { countStock, moveStock, scrapStock, useListLocations } from "@/lib/api/generated/admin-inventory/admin-inventory";
import type { ScrapReason, StockCountOut } from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";
import { SCRAP_REASON_LABELS } from "@/lib/inventory/labels";
import { countLines, countMessage, type CountEntry } from "@/lib/inventory/stock";
import { errorMessage } from "@/lib/i18n/problems";
import { SCRAP_REASONS } from "@/lib/validation/inventory";

import { LabelPrinter } from "./label-printer";
import { useInventoryRefresh } from "./part-dialogs";

/** A model's Ausführung as the dialogs name it. */
export type StockVariant = { variantId: string; title: string; sku: string };
/** A place as the dialogs name it: its code and what people call it. */
export type StockPlace = { code: string; place: string };

/** The places goods may go into, named as people call them ("Regal 2, Boden 3"). */
export function usePlaces(enabled = true) {
  return useListLocations({
    query: { enabled, select: (tree) => tree.items.filter((item) => item.holds_goods) },
  });
}

function Failure({ error }: { error: unknown }) {
  return (
    <p role="alert" className="text-small text-danger empty:hidden">
      {error ? errorMessage(error) : null}
    </p>
  );
}

function wholeNumber(text: string): number | null {
  const value = Number.parseInt(text, 10);
  return Number.isInteger(value) && String(value) === text.trim() ? value : null;
}

/** The places as a select; `none` adds a first choice without a place. */
function PlaceSelect({
  id,
  value,
  onChange,
  none,
  exclude,
}: {
  id: string;
  value: string;
  onChange: (code: string) => void;
  none: string;
  exclude?: string;
}) {
  const places = usePlaces();
  return (
    <Select id={id} value={value} onChange={(event) => onChange(event.target.value)} disabled={places.isPending}>
      <option value="">{places.isPending ? "Wird geladen …" : none}</option>
      {(places.data ?? [])
        .filter((place) => place.code !== exclude)
        .map((place) => (
          <option key={place.id} value={place.code}>
            {place.place === place.code ? place.code : `${place.place} (${place.code})`}
          </option>
        ))}
    </Select>
  );
}

type Done = (message: string) => void;

/** Umlagern: a number of pieces of an Ausführung from one place to another. */
export function MoveStockDialog({
  variant,
  from,
  available,
  trigger,
  onDone,
}: {
  variant: StockVariant;
  from: StockPlace;
  available: number;
  trigger: ReactNode;
  onDone: Done;
}) {
  const [open, setOpen] = useState(false);
  const [quantity, setQuantity] = useState(String(available));
  const [target, setTarget] = useState("");
  const refresh = useInventoryRefresh();
  const count = wholeNumber(quantity);
  const move = useMutation<string, ApiProblem>({
    async mutationFn() {
      const result = await moveStock({
        variant_id: variant.variantId,
        from_location: from.code,
        to_location: target,
        quantity: count ?? 0,
      });
      return `${result.moved} nach ${target} umgelagert.`;
    },
    onSuccess(message) {
      refresh();
      setOpen(false);
      onDone(message);
    },
  });
  const valid = count !== null && count >= 1 && count <= available && target !== "";
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          setQuantity(String(available));
          setTarget("");
          move.reset();
        }
      }}
    >
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogTitle>Umlagern</DialogTitle>
        <DialogDescription>
          {variant.title}, aus {from.place}. Reservierte Stücke behalten ihre Bestellung.
        </DialogDescription>
        <form
          noValidate
          className="mt-6 space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (valid) {
              move.mutate();
            }
          }}
        >
          <FormField label="Anzahl" hint={`Hier liegen ${available}.`}>
            {(control) => (
              <Input {...control} value={quantity} onChange={(event) => setQuantity(event.target.value)} inputMode="numeric" />
            )}
          </FormField>
          <div>
            <label htmlFor="move-target" className="text-small font-medium">
              Nach
            </label>
            <div className="mt-2">
              <PlaceSelect id="move-target" value={target} onChange={setTarget} none="Bitte wählen" exclude={from.code} />
            </div>
          </div>
          <Failure error={move.error} />
          <div className="flex justify-end gap-3">
            <DialogClose asChild>
              <Button type="button" variant="secondary" size="sm">
                Abbrechen
              </Button>
            </DialogClose>
            <Button type="submit" size="sm" disabled={!valid || move.isPending}>
              {move.isPending ? "Wird gebucht …" : "Umlagern"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** Ausbuchen: free pieces with a reason, from a place or the oldest anywhere. */
export function ScrapStockDialog({
  variant,
  location,
  free,
  trigger,
  onDone,
}: {
  variant: StockVariant;
  location: StockPlace | null;
  free: number;
  trigger: ReactNode;
  onDone: Done;
}) {
  const [open, setOpen] = useState(false);
  const [quantity, setQuantity] = useState("1");
  const [reason, setReason] = useState<ScrapReason>("sold");
  const [place, setPlace] = useState(location?.code ?? "");
  const [note, setNote] = useState("");
  const refresh = useInventoryRefresh();
  const count = wholeNumber(quantity);
  const scrap = useMutation<string, ApiProblem>({
    async mutationFn() {
      const result = await scrapStock({
        variant_id: variant.variantId,
        location_code: place === "" ? null : place,
        quantity: count ?? 0,
        reason,
        note: note.trim(),
      });
      return `${result.scrapped} ausgebucht (${SCRAP_REASON_LABELS[reason]}).`;
    },
    onSuccess(message) {
      refresh();
      setOpen(false);
      onDone(message);
    },
  });
  const valid = count !== null && count >= 1;
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          setQuantity("1");
          setReason("sold");
          setPlace(location?.code ?? "");
          setNote("");
          scrap.reset();
        }
      }}
    >
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogTitle>Ausbuchen</DialogTitle>
        <DialogDescription>
          {variant.title}. Nur freie Stücke; reservierte bleiben bei ihrer Bestellung ({free} frei).
        </DialogDescription>
        <form
          noValidate
          className="mt-6 space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (valid) {
              scrap.mutate();
            }
          }}
        >
          <FormField label="Anzahl">
            {(control) => (
              <Input {...control} value={quantity} onChange={(event) => setQuantity(event.target.value)} inputMode="numeric" />
            )}
          </FormField>
          <div>
            <label htmlFor="scrap-stock-reason" className="text-small font-medium">
              Grund
            </label>
            <Select id="scrap-stock-reason" className="mt-2" value={reason} onChange={(event) => setReason(event.target.value as ScrapReason)}>
              {SCRAP_REASONS.map((value) => (
                <option key={value} value={value}>
                  {SCRAP_REASON_LABELS[value]}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label htmlFor="scrap-stock-place" className="text-small font-medium">
              Platz
            </label>
            <div className="mt-2">
              <PlaceSelect id="scrap-stock-place" value={place} onChange={setPlace} none="Egal: die ältesten freien" />
            </div>
          </div>
          <FormField label="Notiz" hint="Optional, z. B. „Messe Leipzig“.">
            {(control) => <Input {...control} value={note} onChange={(event) => setNote(event.target.value)} maxLength={200} />}
          </FormField>
          <Failure error={scrap.error} />
          <div className="flex justify-end gap-3">
            <DialogClose asChild>
              <Button type="button" variant="secondary" size="sm">
                Behalten
              </Button>
            </DialogClose>
            <Button type="submit" size="sm" variant="danger" disabled={!valid || scrap.isPending}>
              {scrap.isPending ? "Wird ausgebucht …" : "Ausbuchen"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** One line to count: what it is, where, and what the Stellwerk shows there. */
export type CountRow = CountEntry & { label: string };

/**
 * Zählen: the number counted per line; the difference is booked in one go. Fewer: free
 * pieces go out as missing. More: new pieces come in. Unchanged lines book nothing.
 */
export function CountDialog({ title, rows, trigger, onDone }: { title: string; rows: readonly CountRow[]; trigger: ReactNode; onDone: Done }) {
  const [open, setOpen] = useState(false);
  const [counted, setCounted] = useState<Record<string, string>>({});
  const refresh = useInventoryRefresh();
  const key = (row: CountRow) => `${row.variantId}@${row.locationCode}`;
  const entries = rows.map((row) => ({ ...row, counted: wholeNumber(counted[key(row)] ?? String(row.expected)) ?? -1 }));
  const valid = entries.every((entry) => entry.counted >= 0);
  const book = useMutation<StockCountOut | null, ApiProblem>({
    async mutationFn() {
      const lines = countLines(entries);
      return lines.length === 0 ? null : await countStock({ lines });
    },
    onSuccess(result) {
      refresh();
      setOpen(false);
      onDone(result === null ? "Alles stimmt, nichts gebucht." : countMessage(result));
    },
    onError(error) {
      if (error.code === "stocktake_outdated") {
        refresh();
      }
    },
  });
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          setCounted({});
          book.reset();
        }
      }}
    >
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogTitle>Zählen: {title}</DialogTitle>
        <DialogDescription>
          Was wirklich daliegt eintragen. Fehlende Stücke werden ausgebucht, zusätzliche eingebucht; der Rest bleibt.
        </DialogDescription>
        <form
          noValidate
          className="mt-6 space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (valid) {
              book.mutate();
            }
          }}
        >
          {rows.length === 0 ? <p className="text-small text-ink-secondary">Hier liegt laut Lager nichts.</p> : null}
          <ul className="divide-y divide-line border-y border-line">
            {rows.map((row) => (
              <li key={key(row)} className="grid grid-cols-[minmax(0,1fr)_auto_5rem] items-center gap-3 py-2.5">
                <label htmlFor={`count-${key(row)}`} className="min-w-0 truncate text-small">
                  {row.label}
                </label>
                <span className="text-hint text-ink-tertiary tabular-nums">bisher {row.expected}</span>
                <Input
                  id={`count-${key(row)}`}
                  value={counted[key(row)] ?? String(row.expected)}
                  onChange={(event) => setCounted((before) => ({ ...before, [key(row)]: event.target.value }))}
                  inputMode="numeric"
                  className="text-center tabular-nums"
                />
              </li>
            ))}
          </ul>
          <Failure error={book.error} />
          <div className="flex justify-end gap-3">
            <DialogClose asChild>
              <Button type="button" variant="secondary" size="sm">
                Abbrechen
              </Button>
            </DialogClose>
            <Button type="submit" size="sm" disabled={!valid || rows.length === 0 || book.isPending}>
              {book.isPending ? "Wird gebucht …" : "Zählung buchen"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** Etiketten drucken: the model's labels, as many as asked; printing books nothing. */
export function ModelLabelsDialog({ variant, quantity, trigger }: { variant: StockVariant; quantity: number; trigger: ReactNode }) {
  const [count, setCount] = useState(String(Math.max(1, quantity)));
  const number = wholeNumber(count);
  const valid = number !== null && number >= 1 && number <= 240;
  return (
    <Dialog onOpenChange={(next) => (next ? setCount(String(Math.max(1, quantity))) : undefined)}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogTitle>Etiketten drucken</DialogTitle>
        <DialogDescription>{variant.title}. Ein Etikett passt auf jedes Stück des Modells.</DialogDescription>
        <div className="mt-6 w-32">
          <FormField label="Anzahl">
            {(control) => <Input {...control} value={count} onChange={(event) => setCount(event.target.value)} inputMode="numeric" />}
          </FormField>
        </div>
        {valid ? (
          <LabelPrinter
            key={number}
            models={[{ variantId: variant.variantId, quantity: number, sku: variant.sku }]}
            className="mt-6 border-t border-line pt-6"
          />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
