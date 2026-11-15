"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { FormError } from "@/components/forms/form-error";
import { SubmitButton } from "@/components/forms/submit-button";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import {
  deleteLocation,
  getGetLocationQueryKey,
  getListLocationsQueryKey,
  renameLocation,
} from "@/lib/api/generated/admin-inventory/admin-inventory";
import type { LocationOut } from "@/lib/api/generated/model";
import { useApiForm } from "@/lib/forms/use-api-form";
import { errorMessage } from "@/lib/i18n/problems";
import { locationRenameSchema } from "@/lib/validation/inventory";

export function LocationRenameDialog({ location, trigger }: { location: LocationOut; trigger: ReactNode }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const { form, onSubmit, formError } = useApiForm({
    schema: locationRenameSchema,
    defaultValues: { name: location.name },
    async submit(values) {
      await renameLocation(location.code, values);
      void queryClient.invalidateQueries({ queryKey: getListLocationsQueryKey() });
      void queryClient.invalidateQueries({ queryKey: getGetLocationQueryKey(location.code) });
      setOpen(false);
    },
  });
  const {
    register,
    formState: { errors, isSubmitting },
  } = form;
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        form.reset({ name: location.name });
      }}
    >
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogTitle>{location.code} umbenennen</DialogTitle>
        <DialogDescription>Nur der Name ändert sich; der Code auf den Etiketten bleibt.</DialogDescription>
        <form noValidate onSubmit={onSubmit} className="mt-6">
          <FormError message={formError?.message} />
          <FormField label="Name" error={errors.name?.message}>
            {(field) => <Input {...field} {...register("name")} maxLength={60} />}
          </FormField>
          <div className="mt-6 flex flex-wrap justify-end gap-3">
            <DialogClose asChild>
              <Button type="button" variant="secondary">
                Abbrechen
              </Button>
            </DialogClose>
            <SubmitButton pending={isSubmitting} pendingLabel="Wird gespeichert …">
              Speichern
            </SubmitButton>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** Removes an empty location; the API refuses one with goods or places below it. */
export function LocationDeleteDialog({
  location,
  trigger,
  onDeleted,
}: {
  location: LocationOut;
  trigger: ReactNode;
  onDeleted: () => void;
}) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  async function remove() {
    setPending(true);
    setProblem(null);
    try {
      await deleteLocation(location.code);
      void queryClient.invalidateQueries({ queryKey: getListLocationsQueryKey() });
      setOpen(false);
      onDeleted();
    } catch (error) {
      setProblem(errorMessage(error));
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        setProblem(null);
      }}
    >
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogTitle>{location.code} entfernen?</DialogTitle>
        <DialogDescription>
          Geht nur, solange nichts darin liegt und keine Plätze darunter hängen. Das alte Etikett am Regal bitte abziehen.
        </DialogDescription>
        <p role="alert" className="mt-4 text-small font-medium text-danger">
          {problem}
        </p>
        <div className="mt-6 flex flex-wrap justify-end gap-3">
          <DialogClose asChild>
            <Button type="button" variant="secondary">
              Behalten
            </Button>
          </DialogClose>
          <Button type="button" variant="danger" onClick={() => void remove()} disabled={pending} aria-busy={pending || undefined}>
            {pending ? "Wird entfernt …" : "Entfernen"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
