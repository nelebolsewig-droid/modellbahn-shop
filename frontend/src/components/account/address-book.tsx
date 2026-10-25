"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { FormError } from "@/components/forms/form-error";
import { SubmitButton } from "@/components/forms/submit-button";
import { AddressFields } from "@/components/shop/address-fields";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
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
import { PendingNotice } from "@/components/ui/pending-notice";
import type { CustomerAddressOut } from "@/lib/api/generated/model";
import {
  addAddress,
  changeAddress,
  getListAddressesQueryKey,
  removeAddress,
  useListAddresses,
} from "@/lib/api/generated/store-account/store-account";
import type { ApiProblem } from "@/lib/api/problem";
import { useApiForm } from "@/lib/forms/use-api-form";
import { errorMessage } from "@/lib/i18n/problems";
import { cn } from "@/lib/utils";
import { bookEntrySchema, EMPTY_ADDRESS, type BookEntryValues, type ShippingCountry } from "@/lib/validation/checkout";

import { CustomerGate } from "./customer-gate";

/** Mirrors ADDRESS_BOOK_MAX_SIZE of the sales module. */
export const ADDRESS_BOOK_SIZE = 20;

const NEW_ENTRY = "new";

/** The address book: saved shipping addresses, one of them preselected at the checkout. */
export function AddressBook() {
  return <CustomerGate pending="Dein Adressbuch wird geladen …">{() => <Book />}</CustomerGate>;
}

function Book() {
  const book = useListAddresses();
  // The entry whose form is open, or NEW_ENTRY; one form at a time.
  const [editing, setEditing] = useState<string | null>(null);

  if (book.isPending) {
    return <PendingNotice className="mt-10">Dein Adressbuch wird geladen …</PendingNotice>;
  }
  if (book.isError) {
    return (
      <Alert tone="danger" title="Dein Adressbuch konnte nicht geladen werden" className="mt-10 max-w-xl">
        <p>{errorMessage(book.error)}</p>
      </Alert>
    );
  }
  const entries = book.data;
  const full = entries.length >= ADDRESS_BOOK_SIZE;

  return (
    <div className="mt-10">
      <p className="text-small text-ink-secondary">
        <span className="tabular-nums">
          {entries.length} von {ADDRESS_BOOK_SIZE}
        </span>{" "}
        Adressen. Die Standardadresse ist an der Kasse vorausgewählt.
      </p>
      <ul className="mt-6 grid items-start gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {entries.map((entry) => (
          <li key={entry.id}>
            {editing === entry.id ? (
              <EntryCard>
                <EntryForm entry={entry} onDone={() => setEditing(null)} />
              </EntryCard>
            ) : (
              <EntryView entry={entry} onEdit={() => setEditing(entry.id)} />
            )}
          </li>
        ))}
        <li className={cn(editing === NEW_ENTRY && "sm:col-span-2 lg:col-span-1")}>
          {editing === NEW_ENTRY ? (
            <EntryCard>
              <EntryForm entry={null} first={entries.length === 0} onDone={() => setEditing(null)} />
            </EntryCard>
          ) : (
            <button
              type="button"
              disabled={full}
              onClick={() => setEditing(NEW_ENTRY)}
              className={cn(
                "flex min-h-48 w-full cursor-pointer flex-col items-center justify-center gap-3 rounded-lg",
                "border border-dashed border-line-strong p-6 text-center transition-colors",
                "hover:border-ink hover:bg-surface disabled:cursor-not-allowed disabled:hover:border-line-strong disabled:hover:bg-transparent",
              )}
            >
              <span aria-hidden="true" className="grid size-10 place-items-center rounded-full border border-line-control text-heading leading-none">
                +
              </span>
              <span className="font-medium">Neue Adresse</span>
              <span className="text-hint text-ink-tertiary">
                {full ? "Das Adressbuch ist voll." : "Für Zuhause, die Werkstatt oder den Verein"}
              </span>
            </button>
          )}
        </li>
      </ul>
    </div>
  );
}

function EntryCard({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn("rounded-lg border border-line bg-surface p-6", className)}>{children}</div>;
}

function useBookUpdate() {
  const queryClient = useQueryClient();
  // Every change answers with the whole book, already in its order.
  return (book: CustomerAddressOut[]) => queryClient.setQueryData(getListAddressesQueryKey(), book);
}

function EntryView({ entry, onEdit }: { entry: CustomerAddressOut; onEdit: () => void }) {
  const storeBook = useBookUpdate();
  const makeDefault = useMutation<CustomerAddressOut[], ApiProblem>({
    mutationFn: () => changeAddress(entry.id, { is_default: true }),
    onSuccess: storeBook,
  });

  return (
    <EntryCard className={cn("flex flex-col", entry.is_default && "border-selected shadow-[inset_0_0_0_1px_var(--selected)]")}>
      <div className="flex items-start justify-between gap-3">
        <p className="label-caps text-ink-tertiary">{entry.label || "Adresse"}</p>
        {entry.is_default ? <Badge tone="accent">Standard</Badge> : null}
      </div>
      <address className="mt-4 flex-1 text-small not-italic">
        <span className="block font-medium">{entry.recipient}</span>
        {entry.street}
        <br />
        {entry.postal_code} {entry.city}
        <br />
        <span className="text-ink-secondary">{entry.country_name}</span>
      </address>
      <p role="alert" className="text-hint font-medium text-danger not-empty:mt-4">
        {makeDefault.isError ? errorMessage(makeDefault.error) : null}
      </p>
      <div className="mt-6 flex flex-wrap gap-x-1 gap-y-2 border-t border-line pt-4">
        <Button type="button" variant="ghost" size="sm" className="px-3" onClick={onEdit}>
          Bearbeiten
        </Button>
        {!entry.is_default ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="px-3"
            disabled={makeDefault.isPending}
            aria-busy={makeDefault.isPending || undefined}
            onClick={() => makeDefault.mutate()}
          >
            Als Standard
          </Button>
        ) : null}
        <RemoveEntry entry={entry} />
      </div>
    </EntryCard>
  );
}

function RemoveEntry({ entry }: { entry: CustomerAddressOut }) {
  const [open, setOpen] = useState(false);
  const storeBook = useBookUpdate();
  const remove = useMutation<CustomerAddressOut[], ApiProblem>({
    mutationFn: () => removeAddress(entry.id),
    onSuccess(book) {
      setOpen(false);
      storeBook(book);
    },
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          remove.reset();
        }
      }}
    >
      <DialogTrigger asChild>
        <Button type="button" variant="ghost" size="sm" className="px-3 text-danger hover:bg-danger-subtle hover:text-danger">
          Löschen
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogTitle>Adresse löschen?</DialogTitle>
        <DialogDescription>
          {entry.recipient}, {entry.street}, {entry.postal_code} {entry.city} verschwindet aus dem Adressbuch. Bestellungen an
          diese Adresse bleiben, wie sie sind.
          {entry.is_default ? " Die älteste übrige Adresse wird Standard." : ""}
        </DialogDescription>
        <p role="alert" className="text-small font-medium text-danger not-empty:mt-4">
          {remove.isError ? errorMessage(remove.error) : null}
        </p>
        <div className="mt-6 flex flex-wrap justify-end gap-3">
          <DialogClose asChild>
            <Button type="button" variant="secondary">
              Behalten
            </Button>
          </DialogClose>
          <Button
            type="button"
            variant="danger"
            disabled={remove.isPending}
            aria-busy={remove.isPending || undefined}
            onClick={() => remove.mutate()}
          >
            {remove.isPending ? "Wird gelöscht …" : "Löschen"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

type EntryFormProps = {
  /** The entry to change; null adds a new one. */
  entry: CustomerAddressOut | null;
  /** The first entry becomes the default anyway. */
  first?: boolean;
  onDone: () => void;
};

function EntryForm({ entry, first = false, onDone }: EntryFormProps) {
  const storeBook = useBookUpdate();
  const defaults: BookEntryValues = entry
    ? {
        label: entry.label,
        recipient: entry.recipient,
        street: entry.street,
        postal_code: entry.postal_code,
        city: entry.city,
        country_code: entry.country_code as ShippingCountry,
        is_default: entry.is_default,
      }
    : { label: "", ...EMPTY_ADDRESS, is_default: first };
  const { form, onSubmit, formError } = useApiForm({
    schema: bookEntrySchema,
    defaultValues: defaults,
    async submit({ label, is_default, ...address }) {
      const book = entry
        ? await changeAddress(entry.id, { label, address, is_default })
        : await addAddress({ label, ...address, is_default });
      storeBook(book);
      onDone();
    },
  });
  const {
    register,
    formState: { errors, isSubmitting },
  } = form;
  // The default stays the default until another entry takes over.
  const defaultFixed = first || (entry?.is_default ?? false);

  return (
    <form noValidate onSubmit={onSubmit} aria-label={entry ? "Adresse bearbeiten" : "Neue Adresse"}>
      <p className="label-caps text-ink-tertiary">{entry ? "Adresse bearbeiten" : "Neue Adresse"}</p>
      <FormError message={formError?.message} className="mt-4" />
      <div className="mt-5 space-y-5">
        <FormField label="Bezeichnung" hint="Optional, z. B. „Werkstatt“" error={errors.label?.message}>
          {(control) => <Input {...control} {...register("label")} maxLength={40} />}
        </FormField>
        <AddressFields register={register} errors={errors} />
        {defaultFixed ? (
          <p className="text-small text-ink-secondary">
            {first ? "Die erste Adresse wird deine Standardadresse." : "Das ist deine Standardadresse."}
          </p>
        ) : (
          <label className="flex items-center gap-3 text-small">
            <input type="checkbox" {...register("is_default")} className="size-4 accent-[var(--selected)]" />
            Als Standardadresse verwenden
          </label>
        )}
      </div>
      <div className="mt-6 flex flex-wrap gap-3">
        <SubmitButton pending={isSubmitting} pendingLabel="Speichert …" size="sm">
          Speichern
        </SubmitButton>
        <Button type="button" variant="secondary" size="sm" onClick={onDone}>
          Abbrechen
        </Button>
      </div>
    </form>
  );
}
