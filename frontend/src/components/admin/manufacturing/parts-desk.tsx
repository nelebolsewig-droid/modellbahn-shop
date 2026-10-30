"use client";

import { useMutation } from "@tanstack/react-query";
import type { Route } from "next";
import Link from "next/link";
import { useDeferredValue, useState, type ReactNode } from "react";
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
  updateMaterial,
  updatePart,
} from "@/lib/api/generated/admin-manufacturing/admin-manufacturing";
import type { ListPartsParams, MaterialOut, PartOut, StaffRole, Technology } from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";
import { useApiForm } from "@/lib/forms/use-api-form";
import { errorMessage } from "@/lib/i18n/problems";
import { formatMinutes, MATERIAL_UNITS, MAY_PLAN, TECHNOLOGY_LABELS } from "@/lib/manufacturing/hall";
import { EMPTY_PART, materialSchema, partSchema, type PartValues } from "@/lib/validation/manufacturing";

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
        die Stücklisten der Bausätze (im Katalog, beim Produkt) und die Platten in der Druckerhalle.
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
      code="FER 10"
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
        {part.plate_minutes !== null ? formatMinutes(part.plate_minutes) : "–"}
        <span className="block text-hint text-ink-tertiary">{part.parts_per_plate} Stück</span>
      </td>
      <td className="py-3 pr-4 text-right align-top tabular-nums">
        {part.minutes_per_part === null
          ? "–"
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

function MaterialsPanel({ mayPlan }: { mayPlan: boolean }) {
  const materials = useMaterials();
  return (
    <Panel title="Material" code="FER 11">
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
            {material.part_count === 1 ? "1 Teil" : `${material.part_count} Teile`}
            {material.active ? "" : " · archiviert"}
          </p>
        </div>
        {mayPlan ? (
          <div className="flex shrink-0 gap-3 pt-1 text-hint font-medium">
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

function NewMaterial() {
  const refresh = useManufacturingRefresh();
  const empty = { name: "", technology: "resin" as const, notes: "" };
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
    formState: { errors, isSubmitting },
  } = form;
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
      <SubmitButton pending={isSubmitting} pendingLabel="Speichert …" size="sm" className="mt-4">
        Material anlegen
      </SubmitButton>
    </form>
  );
}
