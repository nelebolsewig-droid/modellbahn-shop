"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { useWatch } from "react-hook-form";

import { FormError } from "@/components/forms/form-error";
import { SubmitButton } from "@/components/forms/submit-button";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { OptionGroup, OptionPill } from "@/components/ui/option-pill";
import {
  createLocation,
  deleteLocation,
  getGetLocationQueryKey,
  getListLocationsQueryKey,
  renameLocation,
} from "@/lib/api/generated/admin-inventory/admin-inventory";
import type { LocationKind, LocationOut } from "@/lib/api/generated/model";
import { useApiForm } from "@/lib/forms/use-api-form";
import { LOCATION_KIND_LABELS } from "@/lib/inventory/labels";
import { childCode, childKinds } from "@/lib/inventory/locations";
import { errorMessage } from "@/lib/i18n/problems";
import { locationCreateSchema, locationRenameSchema } from "@/lib/validation/inventory";

type Parent = Pick<LocationOut, "code" | "kind" | "name"> | null;

const SEGMENT_EXAMPLES: Readonly<Record<LocationKind, string>> = {
  site: "LAGER",
  shelf: "R01",
  compartment: "F01",
  box: "B01",
  staging: "PACK",
};

/** A new location below `parent`, or a new site; shows the code it will get as you type. */
export function LocationCreateDialog({
  parent,
  trigger,
  onCreated,
}: {
  parent: Parent;
  trigger: ReactNode;
  onCreated?: (location: LocationOut) => void;
}) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const kinds = childKinds(parent);
  const { form, onSubmit, formError } = useApiForm({
    schema: locationCreateSchema,
    defaultValues: { segment: "", kind: kinds[0] ?? "site", name: "" },
    async submit(values) {
      const location = await createLocation({
        segment: values.segment,
        kind: values.kind,
        name: values.name,
        parent_code: parent?.code ?? null,
      });
      void queryClient.invalidateQueries({ queryKey: getListLocationsQueryKey() });
      if (parent) {
        void queryClient.invalidateQueries({ queryKey: getGetLocationQueryKey(parent.code) });
      }
      setOpen(false);
      form.reset();
      onCreated?.(location);
    },
  });
  const {
    register,
    control,
    setValue,
    formState: { errors, isSubmitting },
  } = form;
  const [segment, kind] = useWatch({ control, name: ["segment", "kind"] });
  const preview = segment.trim() === "" ? null : childCode(parent, segment);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          form.reset();
        }
      }}
    >
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogTitle>{parent ? `Platz in ${parent.code} anlegen` : "Lager anlegen"}</DialogTitle>
        <DialogDescription>
          {parent
            ? "Der Code steht später auf dem Etikett am Regal und wird nie mehr geändert."
            : "Ein Lager ist das Gebäude oder der Raum; Regale und Ablagen kommen hinein."}
        </DialogDescription>
        <form noValidate onSubmit={onSubmit} className="mt-6 space-y-5">
          <FormError message={formError?.message} />
          {kinds.length > 1 ? (
            <OptionGroup
              label="Art"
              value={kind}
              onValueChange={(value) => setValue("kind", value as LocationKind, { shouldDirty: true })}
            >
              {kinds.map((option) => (
                <OptionPill key={option} value={option}>
                  {LOCATION_KIND_LABELS[option]}
                </OptionPill>
              ))}
            </OptionGroup>
          ) : null}
          <div className="grid gap-5 sm:grid-cols-[9rem_minmax(0,1fr)]">
            <FormField label="Kürzel" error={errors.segment?.message}>
              {(field) => (
                <Input
                  {...field}
                  {...register("segment")}
                  placeholder={SEGMENT_EXAMPLES[kind]}
                  maxLength={8}
                  autoCapitalize="characters"
                  autoComplete="off"
                  spellCheck={false}
                  className="font-mono uppercase"
                />
              )}
            </FormField>
            <FormField label="Name" hint="Optional, z. B. „Regal am Fenster“." error={errors.name?.message}>
              {(field) => <Input {...field} {...register("name")} maxLength={60} />}
            </FormField>
          </div>
          <div className="flex items-center gap-4 rounded-sm bg-canvas px-4 py-3">
            <span className="label-caps text-ink-tertiary">Code</span>
            <span className="font-mono text-body-lg font-medium tracking-wider">{preview ?? "–"}</span>
          </div>
          <div className="flex flex-wrap justify-end gap-3">
            <DialogClose asChild>
              <Button type="button" variant="secondary">
                Abbrechen
              </Button>
            </DialogClose>
            <SubmitButton pending={isSubmitting} pendingLabel="Wird angelegt …">
              Anlegen
            </SubmitButton>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

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
