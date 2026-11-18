"use client";

import { useMutation } from "@tanstack/react-query";
import type { Route } from "next";
import Link from "next/link";
import { useDeferredValue, useRef, useState, type ReactNode } from "react";
import { Controller } from "react-hook-form";

import { useReferences } from "@/components/admin/catalog/use-product";
import { Panel } from "@/components/admin/panel";
import { FormError } from "@/components/forms/form-error";
import { SubmitButton } from "@/components/forms/submit-button";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { OptionGroup, OptionPill } from "@/components/ui/option-pill";
import { PendingNotice } from "@/components/ui/pending-notice";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  createMaterial,
  createPart,
  deleteMaterial,
  deletePart,
  readSliceFile,
  updateMaterial,
  updatePart,
} from "@/lib/api/generated/admin-manufacturing/admin-manufacturing";
import type {
  ListPartsParams,
  MaterialOut,
  PartOut,
  SliceFileOut,
  StaffRole,
  Technology,
} from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";
import { useApiForm } from "@/lib/forms/use-api-form";
import { errorMessage, fieldErrorMessage } from "@/lib/i18n/problems";
import { centsToEuroInput } from "@/lib/catalog/format";
import { formatMinutes, MATERIAL_UNITS, materialPrice, MAY_PLAN, PRICE_UNITS, TECHNOLOGY_LABELS } from "@/lib/manufacturing/hall";
import { plateValues, printDuration, SLICE_FILE_ACCEPT, sliceHead } from "@/lib/manufacturing/slice-file";
import {
  EMPTY_PART,
  materialPrice as materialPriceSchema,
  materialSchema,
  partSchema,
  type PartValues,
} from "@/lib/validation/manufacturing";

import { useManufacturingRefresh, useMaterials, useParts } from "./use-manufacturing";

const HALL = "/admin/fertigung" as Route;
const decimal = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 2 });

/** The parts that are printed and the materials they are made of. */
export function PartsDesk({ staffRole }: { staffRole: StaffRole }) {
  const mayPlan = MAY_PLAN.has(staffRole);
  return (
    <>
      <Link href={HALL} className="text-small text-accent hover:underline">
        ← Druckerhalle
      </Link>
      <p className="mt-4 label-caps text-ink-tertiary">Fertigung</p>
      <h1 className="mt-3 text-heading sm:text-title">Teile &amp; Material</h1>
      <p className="mt-3 max-w-2xl text-ink-secondary">
        Jedes Teil gehört zu einem Maßstab und einer Drucktechnik und trägt seine Druckdaten. Aus den Teilen entstehen
        die Stücklisten der Bausätze (im Katalog, beim Modell) und die Platten in der Druckerhalle.
      </p>
      <div className="mt-8 grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <PartsPanel mayPlan={mayPlan} />
        <MaterialsPanel mayPlan={mayPlan} />
      </div>
    </>
  );
}

function PartsPanel({ mayPlan }: { mayPlan: boolean }) {
  const references = useReferences();
  const [scale, setScale] = useState("");
  const [technology, setTechnology] = useState<Technology | "">("");
  const [search, setSearch] = useState("");
  const [archived, setArchived] = useState(false);
  const query = useDeferredValue(search.trim());
  const params: ListPartsParams = {
    ...(scale ? { scale } : {}),
    ...(technology ? { technology } : {}),
    ...(query ? { q: query } : {}),
    ...(archived ? { archived } : {}),
  };
  const parts = useParts(params);
  const scales = references.data?.scales ?? [];

  return (
    <Panel
      title="Teile"
     
      actions={
        mayPlan ? (
          <PartDialog
            scales={scales}
            trigger={
              <Button type="button" size="sm">
                Neues Teil
              </Button>
            }
          />
        ) : null
      }
    >
      <div className="grid gap-3 sm:grid-cols-[10rem_10rem_minmax(0,1fr)]">
        <Select value={scale} onChange={(event) => setScale(event.target.value)} aria-label="Maßstab">
          <option value="">Alle Maßstäbe</option>
          {scales.map((option) => (
            <option key={option.code} value={option.code}>
              {option.name}
            </option>
          ))}
        </Select>
        <Select
          value={technology}
          onChange={(event) => setTechnology(event.target.value as Technology | "")}
          aria-label="Drucktechnik"
        >
          <option value="">Jede Technik</option>
          <option value="resin">Resin</option>
          <option value="fdm">Filament</option>
        </Select>
        <Input
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Teilenummer oder Name"
          aria-label="Teile suchen"
        />
      </div>
      <label className="mt-3 flex items-center gap-2 text-small text-ink-secondary">
        <input
          type="checkbox"
          checked={archived}
          onChange={(event) => setArchived(event.target.checked)}
          className="size-4 accent-[var(--selected)]"
        />
        Archivierte zeigen
      </label>

      <div className="mt-5">
        {parts.isPending ? (
          <PendingNotice>Teile werden geladen …</PendingNotice>
        ) : parts.isError ? (
          <p role="alert" className="text-small text-danger">
            {errorMessage(parts.error)}
          </p>
        ) : parts.data.length === 0 ? (
          <p className="text-small text-ink-secondary">
            {query || scale || technology
              ? "Kein Teil passt zu dieser Auswahl."
              : "Noch keine Teile. Leg das erste mit seiner Teilenummer an, etwa STW-ALT-DACH-H0."}
          </p>
        ) : (
          <div className="-mx-5 overflow-x-auto px-5">
            <table className="w-full min-w-[40rem] text-left text-small">
              <thead>
                <tr className="border-b border-line text-hint text-ink-tertiary">
                  <th scope="col" className="py-2 pr-4 font-medium">
                    Teil
                  </th>
                  <th scope="col" className="py-2 pr-4 font-medium">
                    Technik
                  </th>
                  <th scope="col" className="py-2 pr-4 text-right font-medium">
                    Volle Platte
                  </th>
                  <th scope="col" className="py-2 pr-4 text-right font-medium">
                    Je Teil
                  </th>
                  <th scope="col" className="py-2 font-medium">
                    Im Einsatz
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {parts.data.map((part) => (
                  <PartRow key={part.id} part={part} scales={scales} mayPlan={mayPlan} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Panel>
  );
}

function PartRow({
  part,
  scales,
  mayPlan,
}: {
  part: PartOut;
  scales: readonly { code: string; name: string }[];
  mayPlan: boolean;
}) {
  const unit = MATERIAL_UNITS[part.technology];
  const name = (
    <>
      <span className="block font-mono text-hint text-ink-tertiary">
        {part.part_number} · {part.scale_name}
      </span>
      <span className="block font-medium">{part.name}</span>
    </>
  );
  return (
    <tr className={part.active ? undefined : "text-ink-tertiary"}>
      <td className="py-3 pr-4 align-top">
        {mayPlan ? (
          <PartDialog
            part={part}
            scales={scales}
            trigger={
              <button type="button" className="text-left hover:text-accent">
                {name}
              </button>
            }
          />
        ) : (
          name
        )}
        {part.active ? null : <Badge className="mt-1">Archiviert</Badge>}
      </td>
      <td className="py-3 pr-4 align-top">
        <span className="block">{TECHNOLOGY_LABELS[part.technology]}</span>
        <span className="block text-hint text-ink-tertiary">{part.material?.name ?? "kein Material"}</span>
      </td>
      <td className="py-3 pr-4 text-right align-top tabular-nums">
        {part.plate_minutes !== null ? formatMinutes(part.plate_minutes) : "unbekannt"}
        <span className="block text-hint text-ink-tertiary">{part.parts_per_plate} Stück</span>
      </td>
      <td className="py-3 pr-4 text-right align-top tabular-nums">
        {part.minutes_per_part === null
          ? "unbekannt"
          : part.minutes_per_part >= 60
            ? formatMinutes(part.minutes_per_part)
            : `${decimal.format(part.minutes_per_part)} min`}
        <span className="block text-hint text-ink-tertiary">
          {part.material_per_part !== null ? `${decimal.format(part.material_per_part)} ${unit}` : " "}
        </span>
      </td>
      <td className="py-3 align-top text-hint text-ink-secondary">
        {part.bom_count === 0 && part.job_count === 0 ? (
          "noch nicht"
        ) : (
          <>
            <span className="block">{part.bom_count === 1 ? "1 Stückliste" : `${part.bom_count} Stücklisten`}</span>
            <span className="block">{part.job_count === 1 ? "1 Platte" : `${part.job_count} Platten`}</span>
          </>
        )}
      </td>
    </tr>
  );
}

function valuesOf(part: PartOut): PartValues {
  const text = (value: number | null) => (value === null ? "" : String(value).replace(".", ","));
  return {
    part_number: part.part_number,
    name: part.name,
    scale_code: part.scale_code,
    technology: part.technology,
    material_id: part.material?.id ?? "",
    layer_height_um: text(part.layer_height_um),
    plate_minutes: text(part.plate_minutes),
    parts_per_plate: String(part.parts_per_plate),
    material_per_part: text(part.material_per_part),
    notes: part.notes,
    active: part.active,
  };
}

type PartDialogProps = {
  part?: PartOut;
  scales: readonly { code: string; name: string }[];
  trigger: ReactNode;
};

function PartDialog({ part, scales, trigger }: PartDialogProps) {
  const [open, setOpen] = useState(false);
  const refresh = useManufacturingRefresh();
  const materials = useMaterials();
  const remove = useMutation<void, ApiProblem>({
    mutationFn: () => deletePart(part?.id ?? ""),
    onSuccess() {
      refresh();
      setOpen(false);
    },
  });
  const { form, onSubmit, formError } = useApiForm({
    schema: partSchema,
    defaultValues: part ? valuesOf(part) : EMPTY_PART,
    async submit({ scale_code, technology, ...values }) {
      if (part) {
        await updatePart(part.id, values);
      } else {
        await createPart({ ...values, scale_code, technology });
      }
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
  const technology = watch("technology");
  const plate = Number(watch("plate_minutes"));
  const perPlate = Number(watch("parts_per_plate"));
  const share = plate > 0 && perPlate > 0 ? plate / perPlate : null;
  const fitting = (materials.data ?? []).filter(
    (material) => material.technology === technology && (material.active || material.id === part?.material?.id),
  );

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          form.reset(part ? valuesOf(part) : EMPTY_PART);
          remove.reset();
        }
      }}
    >
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogTitle>{part ? part.part_number : "Neues Teil"}</DialogTitle>
        <DialogDescription>
          {part
            ? "Maßstab und Drucktechnik bleiben fest. Ein Teil im Einsatz lässt sich archivieren, aber nicht löschen."
            : "Ein druckbares Einzelteil für einen Maßstab. Die Druckdaten helfen beim Schätzen der Druckzeit."}
        </DialogDescription>
        <form noValidate onSubmit={onSubmit} className="mt-6" aria-label={part ? "Teil bearbeiten" : "Neues Teil"}>
          <FormError message={formError?.message} className="mb-4" />
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Teilenummer" hint="z. B. STW-ALT-DACH-H0" error={errors.part_number?.message}>
              {(field) => (
                <Input
                  {...field}
                  {...register("part_number")}
                  maxLength={40}
                  className="font-mono uppercase"
                  autoComplete="off"
                />
              )}
            </FormField>
            <FormField label="Name" error={errors.name?.message}>
              {(field) => <Input {...field} {...register("name")} maxLength={120} />}
            </FormField>
          </div>
          {part ? (
            <p className="mt-4 text-small text-ink-secondary">
              {part.scale_name} · {TECHNOLOGY_LABELS[part.technology]}
            </p>
          ) : (
            <div className="mt-4 grid gap-4 sm:grid-cols-2 sm:items-end">
              <FormField label="Maßstab" error={errors.scale_code?.message}>
                {(field) => (
                  <Select {...field} {...register("scale_code")}>
                    {scales.map((option) => (
                      <option key={option.code} value={option.code}>
                        {option.name}
                      </option>
                    ))}
                  </Select>
                )}
              </FormField>
              <Controller
                control={control}
                name="technology"
                render={({ field }) => (
                  <OptionGroup
                    label="Drucktechnik"
                    value={field.value}
                    onValueChange={(value) => {
                      field.onChange(value);
                      form.setValue("material_id", "");
                    }}
                  >
                    <OptionPill value="resin">Resin</OptionPill>
                    <OptionPill value="fdm">Filament</OptionPill>
                  </OptionGroup>
                )}
              />
            </div>
          )}
          <FormField label="Material" error={errors.material_id?.message} className="mt-4">
            {(field) => (
              <Select {...field} {...register("material_id")}>
                <option value="">Kein Material angegeben</option>
                {fitting.map((material) => (
                  <option key={material.id} value={material.id}>
                    {material.name}
                  </option>
                ))}
              </Select>
            )}
          </FormField>
          <fieldset className="mt-5">
            <legend className="text-small font-medium">Druckdaten</legend>
            {technology === "resin" ? (
              <SliceFilePicker
                partsPerPlate={perPlate}
                onRead={(plate) => {
                  for (const [name, value] of Object.entries(plateValues(plate, perPlate))) {
                    form.setValue(name as keyof ReturnType<typeof plateValues>, value, {
                      shouldDirty: true,
                      shouldValidate: true,
                    });
                  }
                }}
              />
            ) : null}
            <div className="mt-2 grid gap-4 sm:grid-cols-4">
              <FormField label="Volle Platte (min)" error={errors.plate_minutes?.message}>
                {(field) => (
                  <Input {...field} {...register("plate_minutes")} inputMode="numeric" className="tabular-nums" />
                )}
              </FormField>
              <FormField label="Teile je Platte" error={errors.parts_per_plate?.message}>
                {(field) => (
                  <Input {...field} {...register("parts_per_plate")} inputMode="numeric" className="tabular-nums" />
                )}
              </FormField>
              <FormField label="Schicht (µm)" error={errors.layer_height_um?.message}>
                {(field) => (
                  <Input {...field} {...register("layer_height_um")} inputMode="numeric" className="tabular-nums" />
                )}
              </FormField>
              <FormField
                label={`Material je Teil (${MATERIAL_UNITS[technology]})`}
                error={errors.material_per_part?.message}
              >
                {(field) => (
                  <Input {...field} {...register("material_per_part")} inputMode="decimal" className="tabular-nums" />
                )}
              </FormField>
            </div>
            <p className="mt-2 text-hint text-ink-tertiary">
              {share !== null
                ? `Je Teil ${decimal.format(Math.round(share * 10) / 10)} min Druckzeit.`
                : "Mit Plattenzeit und Teilen je Platte schätzt die Druckerhalle die Dauer einer Platte."}
            </p>
          </fieldset>
          <FormField label="Notiz" error={errors.notes?.message} className="mt-4">
            {(field) => <Textarea {...field} {...register("notes")} rows={2} className="min-h-16" />}
          </FormField>
          {part ? (
            <label className="mt-4 flex items-center gap-3 text-small">
              <input type="checkbox" {...register("active")} className="size-4 accent-[var(--selected)]" />
              Aktiv (archivierte Teile kommen auf keine neue Platte)
            </label>
          ) : null}
          <p role="alert" className="text-small text-danger not-empty:mt-4">
            {remove.isError ? errorMessage(remove.error) : null}
          </p>
          <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
            {part && part.bom_count === 0 && part.job_count === 0 ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="text-danger hover:bg-danger-subtle hover:text-danger"
                disabled={remove.isPending}
                onClick={() => {
                  if (window.confirm(`Teil ${part.part_number} löschen?`)) remove.mutate();
                }}
              >
                Löschen
              </Button>
            ) : (
              <span />
            )}
            <div className="flex gap-3">
              <Button type="button" variant="secondary" size="sm" onClick={() => setOpen(false)}>
                Abbrechen
              </Button>
              <SubmitButton pending={isSubmitting} pendingLabel="Speichert …" size="sm">
                {part ? "Speichern" : "Teil anlegen"}
              </SubmitButton>
            </div>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function sliceError(error: ApiProblem): string {
  const field = error.fieldErrors[0];
  return field ? fieldErrorMessage(field.field, field.code) : errorMessage(error);
}

/**
 * „Aus Druckdatei“: the sliced .ctb from Chitubox fills plate time, layer height and the
 * resin of one part (ADR 0037). Only the head of the file leaves the computer.
 */
function SliceFilePicker({ onRead, partsPerPlate }: { onRead: (plate: SliceFileOut) => void; partsPerPlate: number }) {
  const input = useRef<HTMLInputElement>(null);
  const [read, setRead] = useState<{ name: string; plate: SliceFileOut } | null>(null);
  const reading = useMutation<SliceFileOut, ApiProblem, File>({
    mutationFn: async (file) => readSliceFile({ head: await sliceHead(file) }),
    onSuccess(plate, file) {
      setRead({ name: file.name, plate });
      onRead(plate);
    },
  });
  const parts = partsPerPlate >= 1 ? Math.round(partsPerPlate) : 1;
  return (
    <div className="mt-2 border border-line bg-sunken px-3 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-hint text-ink-secondary">
          Die geslicte Datei aus Chitubox (.ctb) trägt Plattenzeit, Schicht und Harz je Teil ein.
        </p>
        <input
          ref={input}
          type="file"
          accept={SLICE_FILE_ACCEPT}
          className="sr-only"
          aria-label="Druckdatei wählen"
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (file) reading.mutate(file);
          }}
        />
        <Button type="button" variant="secondary" size="sm" disabled={reading.isPending} onClick={() => input.current?.click()}>
          {reading.isPending ? "Liest …" : "Aus Druckdatei"}
        </Button>
      </div>
      {reading.isError ? (
        <p role="alert" className="mt-2 text-hint text-danger">
          {sliceError(reading.error)}
        </p>
      ) : read ? (
        <p className="mt-2 text-hint text-ink" aria-live="polite">
          <span className="font-medium">{read.plate.machine || read.name}</span>
          {" · "}
          <span className="tabular-nums">
            {decimal.format(read.plate.volume_ml)} ml · {decimal.format(read.plate.grams)} g ·{" "}
            {printDuration(read.plate.print_seconds)}
          </span>
          {" · "}
          {parts > 1
            ? `geteilt durch ${parts} Teile je Platte`
            : "die ganze Platte als ein Teil: Teile je Platte anpassen, wenn mehrere darauf liegen"}
        </p>
      ) : null}
    </div>
  );
}

function MaterialsPanel({ mayPlan }: { mayPlan: boolean }) {
  const materials = useMaterials();
  return (
    <Panel title="Material">
      {materials.isPending ? (
        <PendingNotice>Material wird geladen …</PendingNotice>
      ) : materials.isError ? (
        <p role="alert" className="text-small text-danger">
          {errorMessage(materials.error)}
        </p>
      ) : materials.data.length === 0 ? (
        <p className="text-small text-ink-secondary">
          Noch kein Material. Filament oder Resin, wie die Werkstatt es nennt.
        </p>
      ) : (
        <ul className="divide-y divide-line">
          {materials.data.map((material) => (
            <MaterialRow key={material.id} material={material} mayPlan={mayPlan} />
          ))}
        </ul>
      )}
      {mayPlan ? <NewMaterial /> : null}
    </Panel>
  );
}

function MaterialRow({ material, mayPlan }: { material: MaterialOut; mayPlan: boolean }) {
  const refresh = useManufacturingRefresh();
  const toggle = useMutation<MaterialOut, ApiProblem>({
    mutationFn: () =>
      updateMaterial(material.id, { name: material.name, notes: material.notes, active: !material.active }),
    onSuccess: refresh,
  });
  const remove = useMutation<void, ApiProblem>({
    mutationFn: () => deleteMaterial(material.id),
    onSuccess: refresh,
  });
  const failure = toggle.error ?? remove.error;
  return (
    <li className="py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className={material.active ? "font-medium" : "font-medium text-ink-tertiary"}>{material.name}</p>
          <p className="text-hint text-ink-tertiary">
            {TECHNOLOGY_LABELS[material.technology]} ·{" "}
            {material.part_count === 1 ? "1 Teil" : `${material.part_count} Teile`} ·{" "}
            <span className={material.price_cents === null ? "text-warning" : "text-ink-secondary tabular-nums"}>
              {materialPrice(material.price_cents, material.technology)}
            </span>
            {material.active ? "" : " · archiviert"}
          </p>
        </div>
        {mayPlan ? (
          <div className="flex shrink-0 gap-3 pt-1 text-hint font-medium">
            <MaterialPriceDialog material={material} />
            <button
              type="button"
              className="text-accent hover:underline disabled:text-ink-disabled"
              disabled={toggle.isPending}
              onClick={() => toggle.mutate()}
            >
              {material.active ? "Archivieren" : "Aktivieren"}
            </button>
            {material.part_count === 0 ? (
              <button
                type="button"
                className="text-danger hover:underline disabled:text-ink-disabled"
                disabled={remove.isPending}
                onClick={() => {
                  if (window.confirm(`Material „${material.name}“ löschen?`)) remove.mutate();
                }}
              >
                Löschen
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
      <p role="alert" className="text-hint text-danger not-empty:mt-1">
        {failure ? errorMessage(failure) : null}
      </p>
    </li>
  );
}

/**
 * The price of a litre or kilogram, as the bill or the slicer shows it: with each part's
 * amount it gives what a kit costs to print, the Herstellwert of the store (ADR 0035).
 */
function MaterialPriceDialog({ material }: { material: MaterialOut }) {
  const refresh = useManufacturingRefresh();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const parsed = materialPriceSchema.safeParse(text);
  const save = useMutation<MaterialOut, ApiProblem, number | null>({
    mutationFn: (price) =>
      updateMaterial(material.id, { name: material.name, notes: material.notes, active: material.active, price_cents: price }),
    onSuccess() {
      refresh();
      setOpen(false);
    },
  });
  const unit = PRICE_UNITS[material.technology];
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          setText(material.price_cents === null ? "" : centsToEuroInput(material.price_cents));
          save.reset();
        }
      }}
    >
      <DialogTrigger asChild>
        <button type="button" className="text-accent hover:underline">
          Preis
        </button>
      </DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogTitle>Preis von {material.name}</DialogTitle>
        <DialogDescription>
          Was ein {unit} kostet, brutto. Mit der Menge je Teil ergibt das die Herstellkosten der Modelle im Lagerwert.
        </DialogDescription>
        <form
          noValidate
          className="mt-6"
          onSubmit={(event) => {
            event.preventDefault();
            if (parsed.success) {
              save.mutate(parsed.data);
            }
          }}
        >
          <FormField
            label={`Preis je ${unit} in Euro`}
            hint="Leer lassen, wenn er nicht bekannt ist."
            error={text.trim() !== "" && !parsed.success ? parsed.error.issues[0]?.message : undefined}
          >
            {(field) => (
              <Input {...field} value={text} onChange={(event) => setText(event.target.value)} inputMode="decimal" placeholder="z. B. 39,90" className="w-40" />
            )}
          </FormField>
          <p role="alert" className="text-small text-danger not-empty:mt-3">
            {save.error ? errorMessage(save.error) : null}
          </p>
          <div className="mt-6 flex justify-end">
            <SubmitButton pending={save.isPending} pendingLabel="Speichert …" size="sm" disabled={!parsed.success}>
              Preis speichern
            </SubmitButton>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function NewMaterial() {
  const refresh = useManufacturingRefresh();
  const empty = { name: "", technology: "resin" as const, notes: "", price_cents: "" };
  const { form, onSubmit, formError } = useApiForm({
    schema: materialSchema,
    defaultValues: empty,
    async submit(values) {
      await createMaterial(values);
      form.reset(empty);
      refresh();
    },
  });
  const {
    register,
    control,
    watch,
    formState: { errors, isSubmitting },
  } = form;
  const technology = watch("technology");
  return (
    <form noValidate onSubmit={onSubmit} className="mt-5 border-t border-line pt-5" aria-label="Neues Material">
      <FormError message={formError?.message} className="mb-3" />
      <FormField label="Neues Material" hint="z. B. Resin grau, PLA schwarz" error={errors.name?.message}>
        {(field) => <Input {...field} {...register("name")} maxLength={60} />}
      </FormField>
      <Controller
        control={control}
        name="technology"
        render={({ field }) => (
          <OptionGroup label="Drucktechnik" value={field.value} onValueChange={field.onChange} className="mt-4">
            <OptionPill value="resin">Resin</OptionPill>
            <OptionPill value="fdm">Filament</OptionPill>
          </OptionGroup>
        )}
      />
      <FormField
        label={`Preis je ${PRICE_UNITS[technology]} (optional)`}
        hint="Brutto in Euro, z. B. 39,90. Daraus rechnet das Lager den Herstellwert."
        error={errors.price_cents?.message}
        className="mt-4"
      >
        {(field) => <Input {...field} {...register("price_cents")} inputMode="decimal" className="w-40" />}
      </FormField>
      <SubmitButton pending={isSubmitting} pendingLabel="Speichert …" size="sm" className="mt-4">
        Material anlegen
      </SubmitButton>
    </form>
  );
}
