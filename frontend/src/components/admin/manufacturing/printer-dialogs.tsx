"use client";

import { useState, type ReactNode } from "react";
import { Controller } from "react-hook-form";

import { FormError } from "@/components/forms/form-error";
import { SubmitButton } from "@/components/forms/submit-button";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { OptionGroup, OptionPill } from "@/components/ui/option-pill";
import { SignalLamp, type LampColor } from "@/components/ui/signal-lamp";
import { Textarea } from "@/components/ui/textarea";
import {
  createPrinter,
  reportPrinterStatus,
  updatePrinter,
} from "@/lib/api/generated/admin-manufacturing/admin-manufacturing";
import type { PrinterOut, PrinterStatus, PrintJobOut } from "@/lib/api/generated/model";
import { useApiForm } from "@/lib/forms/use-api-form";
import { jobTitle, PRINTER_STATUS_LABELS, TECHNOLOGY_LABELS } from "@/lib/manufacturing/hall";
import { EMPTY_PRINTER, printerSchema, statusReportSchema, type PrinterValues } from "@/lib/validation/manufacturing";

import { useManufacturingRefresh } from "./use-manufacturing";

function valuesOf(printer: PrinterOut): PrinterValues {
  const size = (value: number | null) => (value === null ? "" : String(value));
  return {
    code: printer.code,
    name: printer.name,
    model: printer.model,
    technology: printer.technology,
    build_x_mm: size(printer.build_x_mm),
    build_y_mm: size(printer.build_y_mm),
    build_z_mm: size(printer.build_z_mm),
    notes: printer.notes,
  };
}

type PrinterDialogProps = {
  /** The printer to change; absent for a new one. */
  printer?: PrinterOut;
  trigger: ReactNode;
  onSaved?: (printer: PrinterOut) => void;
};

/** Add a printer or change one: its code on the label, name, model and build volume. */
export function PrinterDialog({ printer, trigger, onSaved }: PrinterDialogProps) {
  const [open, setOpen] = useState(false);
  const refresh = useManufacturingRefresh();
  const { form, onSubmit, formError } = useApiForm({
    schema: printerSchema,
    defaultValues: printer ? valuesOf(printer) : EMPTY_PRINTER,
    async submit({ technology, ...values }) {
      const saved = printer ? await updatePrinter(printer.id, values) : await createPrinter({ ...values, technology });
      refresh();
      onSaved?.(saved);
      setOpen(false);
      form.reset(printer ? valuesOf(saved) : EMPTY_PRINTER);
    },
  });
  const {
    register,
    control,
    formState: { errors, isSubmitting },
  } = form;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) form.clearErrors();
      }}
    >
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-w-xl">
        <DialogTitle>{printer ? `${printer.code} bearbeiten` : "Drucker hinzufügen"}</DialogTitle>
        <DialogDescription>
          {printer
            ? "Die Drucktechnik bleibt fest; alles andere lässt sich ändern."
            : "Der Code steht auf dem Etikett am Drucker, etwa D01 bis D12. Ein neuer Drucker ist gleich in Betrieb."}
        </DialogDescription>
        <form
          noValidate
          onSubmit={onSubmit}
          className="mt-6"
          aria-label={printer ? "Drucker bearbeiten" : "Neuer Drucker"}
        >
          <FormError message={formError?.message} className="mb-4" />
          <div className="grid gap-4 sm:grid-cols-[8rem_minmax(0,1fr)]">
            <FormField label="Code" error={errors.code?.message}>
              {(field) => (
                <Input
                  {...field}
                  {...register("code")}
                  maxLength={8}
                  autoComplete="off"
                  className="font-mono uppercase"
                />
              )}
            </FormField>
            <FormField label="Name" hint="z. B. Saturn links" error={errors.name?.message}>
              {(field) => <Input {...field} {...register("name")} maxLength={60} />}
            </FormField>
          </div>
          {printer ? (
            <p className="mt-4 text-small text-ink-secondary">
              Drucktechnik: <span className="font-medium text-ink">{TECHNOLOGY_LABELS[printer.technology]}</span>
            </p>
          ) : (
            <Controller
              control={control}
              name="technology"
              render={({ field }) => (
                <OptionGroup label="Drucktechnik" value={field.value} onValueChange={field.onChange} className="mt-5">
                  <OptionPill value="resin">Resin</OptionPill>
                  <OptionPill value="fdm">Filament</OptionPill>
                </OptionGroup>
              )}
            />
          )}
          <FormField label="Modell" hint="Hersteller und Typ" error={errors.model?.message} className="mt-4">
            {(field) => <Input {...field} {...register("model")} maxLength={80} placeholder="Elegoo Saturn 4 Ultra" />}
          </FormField>
          <fieldset className="mt-4">
            <legend className="text-small font-medium">Bauraum in mm</legend>
            <div className="mt-2 grid grid-cols-3 gap-3">
              {(["build_x_mm", "build_y_mm", "build_z_mm"] as const).map((name, index) => (
                <FormField key={name} label={["Breite", "Tiefe", "Höhe"][index]} error={errors[name]?.message}>
                  {(field) => <Input {...field} {...register(name)} inputMode="numeric" className="tabular-nums" />}
                </FormField>
              ))}
            </div>
          </fieldset>
          <FormField label="Notiz" error={errors.notes?.message} className="mt-4">
            {(field) => <Textarea {...field} {...register("notes")} rows={2} className="min-h-16" />}
          </FormField>
          <div className="mt-6 flex flex-wrap justify-end gap-3">
            <Button type="button" variant="secondary" size="sm" onClick={() => setOpen(false)}>
              Abbrechen
            </Button>
            <SubmitButton pending={isSubmitting} pendingLabel="Speichert …" size="sm">
              {printer ? "Speichern" : "Drucker anlegen"}
            </SubmitButton>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

const STATUS_OPTIONS: readonly { status: PrinterStatus; lamp: LampColor; hint: string }[] = [
  { status: "in_service", lamp: "green", hint: "Druckt und nimmt Aufträge an." },
  { status: "defective", lamp: "red", hint: "Kaputt; ein laufender Druck gilt als Fehldruck." },
  { status: "in_repair", lamp: "yellow", hint: "Wird repariert oder gewartet." },
  { status: "retired", lamp: "off", hint: "Steht nicht mehr in der Werkstatt." },
];

type StatusDialogProps = {
  printer: PrinterOut;
  /** The plate on the printer right now, if any. */
  printing: PrintJobOut | null;
  trigger: ReactNode;
  /** Preselects a state, e.g. "Wieder in Betrieb". */
  initialStatus?: PrinterStatus;
};

/** Report what state a printer is in, with a short note why. */
export function StatusDialog({ printer, printing, trigger, initialStatus }: StatusDialogProps) {
  const [open, setOpen] = useState(false);
  const refresh = useManufacturingRefresh();
  const defaults = { status: initialStatus ?? printer.status, note: initialStatus ? "" : printer.status_note };
  const { form, onSubmit, formError } = useApiForm({
    schema: statusReportSchema,
    defaultValues: defaults,
    async submit(values) {
      await reportPrinterStatus(printer.id, values);
      refresh();
      setOpen(false);
    },
  });
  const {
    register,
    control,
    watch,
    formState: { errors, isSubmitting },
  } = form;
  const chosen = watch("status");

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) form.reset(defaults);
      }}
    >
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogTitle>Zustand von {printer.code}</DialogTitle>
        <DialogDescription>Was ist mit dem Drucker? Der Verlauf hält fest, wer es wann gemeldet hat.</DialogDescription>
        <form noValidate onSubmit={onSubmit} className="mt-6" aria-label={`Zustand von ${printer.code} melden`}>
          <FormError message={formError?.message} className="mb-4" />
          <Controller
            control={control}
            name="status"
            render={({ field }) => (
              <fieldset>
                <legend className="sr-only">Zustand</legend>
                <div className="grid gap-2">
                  {STATUS_OPTIONS.map((option) => (
                    <label
                      key={option.status}
                      className="flex cursor-pointer items-start gap-3 rounded-sm border border-line px-4 py-3 transition-colors hover:border-ink-secondary has-checked:border-selected has-checked:bg-sunken"
                    >
                      <input
                        type="radio"
                        name={field.name}
                        value={option.status}
                        checked={field.value === option.status}
                        onChange={() => field.onChange(option.status)}
                        className="mt-1 size-4 accent-[var(--selected)]"
                      />
                      <span className="min-w-0">
                        <span className="flex items-center gap-2 font-medium">
                          <SignalLamp color={option.lamp} />
                          {PRINTER_STATUS_LABELS[option.status]}
                        </span>
                        <span className="mt-0.5 block text-small text-ink-secondary">{option.hint}</span>
                      </span>
                    </label>
                  ))}
                </div>
              </fieldset>
            )}
          />
          {printing !== null && chosen === "defective" ? (
            <p className="mt-4 rounded-sm bg-danger-subtle px-4 py-3 text-small text-danger">
              {jobTitle(printing)} läuft gerade auf {printer.code} und wird als Fehldruck gebucht.
            </p>
          ) : null}
          <FormField
            label="Hinweis"
            hint="z. B. Düse verstopft, Ersatzteil bestellt"
            error={errors.note?.message}
            className="mt-5"
          >
            {(field) => <Input {...field} {...register("note")} maxLength={200} autoComplete="off" />}
          </FormField>
          <div className="mt-6 flex flex-wrap justify-end gap-3">
            <Button type="button" variant="secondary" size="sm" onClick={() => setOpen(false)}>
              Abbrechen
            </Button>
            <SubmitButton pending={isSubmitting} pendingLabel="Meldet …" size="sm">
              Melden
            </SubmitButton>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
