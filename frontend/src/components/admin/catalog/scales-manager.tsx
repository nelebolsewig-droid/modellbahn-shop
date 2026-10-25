"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useWatch } from "react-hook-form";

import { Panel } from "@/components/admin/panel";
import { FormError } from "@/components/forms/form-error";
import { SubmitButton } from "@/components/forms/submit-button";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { PendingNotice } from "@/components/ui/pending-notice";
import { ScaleRule } from "@/components/ui/scale-rule";
import { SpecLine } from "@/components/ui/spec-line";
import { createScale, deleteScale, listScales, updateScale } from "@/lib/api/generated/admin-catalog/admin-catalog";
import type { AdminScaleOut } from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";
import { formatMillimetres } from "@/lib/catalog/format";
import { millimetresPerMetre, scaleLabel } from "@/lib/catalog/scales";
import { useApiForm } from "@/lib/forms/use-api-form";
import { errorMessage } from "@/lib/i18n/problems";
import { scaleRatio, scaleSchema, type ScaleValues } from "@/lib/validation/catalog";

import { REFERENCES_KEY } from "./use-product";

export const SCALES_KEY = ["admin", "scales"] as const;

const decimal = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 1, useGrouping: false });

/** The ratio as the form shows it: 22.5 → "22,5". */
function ratioInput(value: number): string {
  return decimal.format(value);
}

function useRefresh() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: SCALES_KEY });
    // The product editor offers the scales; it must see the new list.
    void queryClient.invalidateQueries({ queryKey: REFERENCES_KEY });
  };
}

/**
 * The scales of the shop: Z to G and the road scales such as 1:24. The shop's catalogue
 * starts with them; the smallest models come first. A scale nothing uses can go.
 */
export function ScalesManager() {
  const scales = useQuery<AdminScaleOut[], ApiProblem>({
    queryKey: SCALES_KEY,
    queryFn: ({ signal }) => listScales({ signal }),
  });
  const longest = Math.max(1, ...(scales.data ?? []).map((scale) => millimetresPerMetre(scale.ratio_denominator)));

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <Panel title="Maßstäbe" code="KAT 04">
        {scales.isPending ? (
          <PendingNotice>Maßstäbe werden geladen …</PendingNotice>
        ) : scales.isError ? (
          <p role="alert" className="text-small text-danger">
            {errorMessage(scales.error)}
          </p>
        ) : (
          <ul className="divide-y divide-line">
            {scales.data.map((scale) => (
              <ScaleRow key={scale.code} scale={scale} longest={longest} />
            ))}
          </ul>
        )}
      </Panel>
      <NewScaleForm longest={longest} />
    </div>
  );
}

function ScaleRow({ scale, longest }: { scale: AdminScaleOut; longest: number }) {
  const refresh = useRefresh();
  const [editing, setEditing] = useState(false);
  const remove = useMutation<void, ApiProblem>({
    mutationFn: () => deleteScale(scale.code),
    onSuccess: refresh,
  });

  if (editing) {
    return (
      <li className="py-4">
        <ScaleForm
          scale={scale}
          longest={longest}
          onDone={() => {
            setEditing(false);
            refresh();
          }}
          onCancel={() => setEditing(false)}
        />
      </li>
    );
  }
  const used = scale.product_count > 0;
  return (
    <li className="grid gap-x-6 gap-y-3 py-4 sm:grid-cols-[6rem_minmax(0,1fr)_auto] sm:items-center">
      <span>
        <span className="block text-heading leading-none font-extralight">{scale.name}</span>
        <span className="mt-1 block font-mono text-hint text-ink-tertiary">Code {scale.code}</span>
      </span>
      <span className="min-w-0">
        <SpecLine
          values={[
            scale.ratio,
            scale.track_gauge_mm === null ? "ohne Gleis" : `Gleis ${formatMillimetres(scale.track_gauge_mm)}`,
            used ? (scale.product_count === 1 ? "1 Produkt" : `${scale.product_count} Produkte`) : "unbenutzt",
          ]}
          size="small"
        />
        <ScaleRule ratioDenominator={scale.ratio_denominator} longestMillimetres={longest} className="mt-2 max-w-sm" />
      </span>
      <span className="flex flex-wrap items-center gap-1 sm:justify-end">
        <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(true)}>
          Bearbeiten
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="text-danger hover:bg-danger-subtle hover:text-danger"
          disabled={used || remove.isPending}
          title={used ? "Produkte gibt es in diesem Maßstab; er bleibt." : undefined}
          onClick={() => {
            if (window.confirm(`Maßstab ${scaleLabel(scale)} löschen?`)) {
              remove.mutate();
            }
          }}
        >
          Löschen
        </Button>
        <span role="alert" className="w-full text-hint text-danger empty:hidden sm:text-right">
          {remove.isError ? errorMessage(remove.error) : null}
        </span>
      </span>
    </li>
  );
}

type ScaleFormProps = {
  /** The scale to change; absent for a new one. */
  scale?: AdminScaleOut;
  longest: number;
  onDone: () => void;
  onCancel?: () => void;
};

function ScaleForm({ scale, longest, onDone, onCancel }: ScaleFormProps) {
  const { form, onSubmit, formError } = useApiForm({
    schema: scaleSchema,
    defaultValues: {
      code: scale?.code ?? "",
      name: scale?.name ?? "",
      ratio_denominator: scale ? ratioInput(scale.ratio_denominator) : "",
      track_gauge_mm:
        scale === undefined || scale.track_gauge_mm === null ? "" : ratioInput(scale.track_gauge_mm),
    } satisfies ScaleValues,
    async submit(values) {
      if (scale) {
        const { code: _code, ...changes } = values;
        await updateScale(scale.code, changes);
      } else {
        await createScale(values);
        form.reset();
      }
      onDone();
    },
  });
  const {
    register,
    control,
    formState: { errors, isSubmitting },
  } = form;
  // A live preview: the tape grows and shrinks while the ratio is typed.
  const typedRatio = scaleRatio.safeParse(useWatch({ control, name: "ratio_denominator" }));

  return (
    <form noValidate onSubmit={onSubmit} aria-label={scale ? `Maßstab ${scale.name} bearbeiten` : "Neuer Maßstab"}>
      <FormError message={formError?.message} className="mb-4" />
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField
          label="Code"
          hint={scale ? "Steht in Artikelnummern und Adressen und bleibt." : "Steht in Artikelnummern und Adressen, z. B. 124; später nicht änderbar."}
          error={errors.code?.message}
        >
          {/* Read-only, not disabled: a disabled field would send no value at all. */}
          {(control) => (
            <Input
              {...control}
              {...register("code")}
              readOnly={scale !== undefined}
              maxLength={4}
              className="font-mono uppercase read-only:bg-sunken read-only:text-ink-secondary"
            />
          )}
        </FormField>
        <FormField label="Name" hint="Wie der Shop ihn zeigt, z. B. H0 oder 1:24" error={errors.name?.message}>
          {(control) => <Input {...control} {...register("name")} maxLength={20} />}
        </FormField>
        <FormField label="Verhältnis 1:" hint="z. B. 87 oder 22,5" error={errors.ratio_denominator?.message}>
          {(control) => <Input {...control} {...register("ratio_denominator")} inputMode="decimal" />}
        </FormField>
        <FormField label="Spurweite in mm" hint="Leer für Straßenfahrzeuge" error={errors.track_gauge_mm?.message}>
          {(control) => <Input {...control} {...register("track_gauge_mm")} inputMode="decimal" />}
        </FormField>
      </div>
      {typedRatio.success ? (
        <ScaleRule ratioDenominator={typedRatio.data} longestMillimetres={Math.max(longest, millimetresPerMetre(typedRatio.data))} className="mt-5" />
      ) : null}
      <div className="mt-5 flex flex-wrap gap-3">
        <SubmitButton pending={isSubmitting} pendingLabel="Speichert …" size="sm">
          {scale ? "Speichern" : "Maßstab anlegen"}
        </SubmitButton>
        {onCancel ? (
          <Button type="button" variant="secondary" size="sm" onClick={onCancel}>
            Abbrechen
          </Button>
        ) : null}
      </div>
    </form>
  );
}

function NewScaleForm({ longest }: { longest: number }) {
  const refresh = useRefresh();
  return (
    <Panel title="Neuer Maßstab" code="KAT 05">
      <ScaleForm longest={longest} onDone={refresh} />
    </Panel>
  );
}
