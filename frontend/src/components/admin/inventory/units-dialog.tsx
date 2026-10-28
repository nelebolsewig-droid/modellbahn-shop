"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useDeferredValue, useState, type ReactNode } from "react";

import { useProduct, useReferences } from "@/components/admin/catalog/use-product";
import { FormError } from "@/components/forms/form-error";
import { SubmitButton } from "@/components/forms/submit-button";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { useListProducts } from "@/lib/api/generated/admin-catalog/admin-catalog";
import {
  getListLocationsQueryKey,
  getListStockQueryKey,
  labelUnits,
  useListLocations,
} from "@/lib/api/generated/admin-inventory/admin-inventory";
import type { UnitOut } from "@/lib/api/generated/model";
import { formatPrice } from "@/lib/catalog/format";
import { useApiForm } from "@/lib/forms/use-api-form";
import { formatUnitCode } from "@/lib/inventory/codes";
import { errorMessage } from "@/lib/i18n/problems";
import { cn } from "@/lib/utils";
import { unitsCreateSchema } from "@/lib/validation/inventory";

import { LabelPrinter } from "./label-printer";

export type ChosenVariant = { variantId: string; title: string; sku: string };

type UnitsDialogProps = {
  /** Opened from a stock line: the article is already known. */
  variant?: ChosenVariant;
  trigger: ReactNode;
};

/**
 * Records new pieces (fresh from the workbench or a delivery): each gets its own code
 * and a label. They can go into a location at once or wait for the scanner.
 */
export function UnitsDialog({ variant, trigger }: UnitsDialogProps) {
  const [open, setOpen] = useState(false);
  const [created, setCreated] = useState<{ units: UnitOut[]; variant: ChosenVariant } | null>(null);
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          setCreated(null);
        }
      }}
    >
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-w-2xl">
        {created === null ? (
          <RecordUnits preset={variant} onCreated={(units, chosen) => setCreated({ units, variant: chosen })} onCancel={() => setOpen(false)} />
        ) : (
          <PrintNewLabels units={created.units} variant={created.variant} onClose={() => setOpen(false)} />
        )}
      </DialogContent>
    </Dialog>
  );
}

function RecordUnits({
  preset,
  onCreated,
  onCancel,
}: {
  preset?: ChosenVariant;
  onCreated: (units: UnitOut[], variant: ChosenVariant) => void;
  onCancel: () => void;
}) {
  const queryClient = useQueryClient();
  const [chosen, setChosen] = useState<ChosenVariant | null>(preset ?? null);
  const locations = useListLocations({ query: { select: (tree) => tree.items.filter((item) => item.holds_goods) } });
  const { form, onSubmit, formError } = useApiForm({
    schema: unitsCreateSchema,
    defaultValues: { variant_id: preset?.variantId ?? "", quantity: "1", location_code: "" },
    async submit(values) {
      const batch = await labelUnits({
        variant_id: values.variant_id,
        quantity: values.quantity,
        location_code: values.location_code === "" ? null : values.location_code,
      });
      void queryClient.invalidateQueries({ queryKey: getListStockQueryKey() });
      void queryClient.invalidateQueries({ queryKey: getListLocationsQueryKey() });
      onCreated(batch.items, chosen as ChosenVariant);
    },
  });
  const {
    register,
    setValue,
    formState: { errors, isSubmitting },
  } = form;

  const choose = (next: ChosenVariant | null) => {
    setChosen(next);
    setValue("variant_id", next?.variantId ?? "", { shouldValidate: next !== null });
  };

  return (
    <>
      <DialogTitle>Einheiten erfassen</DialogTitle>
      <DialogDescription>
        Jedes Stück bekommt einen eigenen Code und ein Etikett mit EAN für die Kasse. Danach geht es direkt zum Druck.
      </DialogDescription>
      <form noValidate onSubmit={onSubmit} className="mt-6 space-y-5">
        <FormError message={formError?.message} />
        <input type="hidden" {...register("variant_id")} />
        {chosen ? (
          <div className="flex items-center justify-between gap-4 rounded-sm border border-line bg-canvas px-4 py-3">
            <div className="min-w-0">
              <p className="label-caps text-ink-tertiary">Artikel</p>
              <p className="mt-1 truncate text-small font-medium">{chosen.title}</p>
              <p className="font-mono text-hint text-ink-tertiary">{chosen.sku}</p>
            </div>
            <Button type="button" size="sm" variant="ghost" onClick={() => choose(null)}>
              Ändern
            </Button>
          </div>
        ) : (
          <VariantPicker onChoose={choose} error={errors.variant_id?.message} />
        )}
        <div className="grid gap-5 sm:grid-cols-[8rem_minmax(0,1fr)]">
          <FormField label="Stück" error={errors.quantity?.message}>
            {(control) => <Input {...control} {...register("quantity")} type="number" inputMode="numeric" min={1} max={200} />}
          </FormField>
          <FormField
            label="Platz"
            hint="Ohne Platz warten die Stücke mit Etikett, bis jemand sie einlagert."
            error={errors.location_code?.message}
          >
            {(control) => (
              <Select {...control} {...register("location_code")} disabled={locations.isPending}>
                <option value="">Später beim Einlagern scannen</option>
                {(locations.data ?? []).map((location) => (
                  <option key={location.id} value={location.code}>
                    {location.code}
                    {location.name ? ` · ${location.name}` : ""}
                  </option>
                ))}
              </Select>
            )}
          </FormField>
        </div>
        <div className="flex flex-wrap justify-end gap-3 pt-2">
          <Button type="button" variant="secondary" onClick={onCancel}>
            Abbrechen
          </Button>
          <SubmitButton pending={isSubmitting} pendingLabel="Wird erfasst …">
            Erfassen und Etiketten drucken
          </SubmitButton>
        </div>
      </form>
    </>
  );
}

/** Find the product by name or number, then pick scale and finish. */
function VariantPicker({ onChoose, error }: { onChoose: (variant: ChosenVariant) => void; error?: string }) {
  const [search, setSearch] = useState("");
  const query = useDeferredValue(search.trim());
  const [productId, setProductId] = useState<string | null>(null);
  const products = useListProducts({ q: query || null, limit: 8 });

  return (
    <div className="space-y-3">
      <FormField label="Artikel suchen" error={error}>
        {(control) => (
          <Input
            {...control}
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setProductId(null);
            }}
            placeholder="Name oder Nummer, z. B. Stellwerk"
            autoComplete="off"
          />
        )}
      </FormField>
      {productId === null ? (
        <ul className="max-h-56 divide-y divide-line overflow-y-auto rounded-sm border border-line">
          {products.isPending ? <li className="px-4 py-3 text-small text-ink-secondary">Wird gesucht …</li> : null}
          {products.isError ? <li className="px-4 py-3 text-small text-danger">{errorMessage(products.error)}</li> : null}
          {products.data?.items.length === 0 ? (
            <li className="px-4 py-3 text-small text-ink-secondary">Kein Artikel gefunden.</li>
          ) : null}
          {products.data?.items.map((product) => (
            <li key={product.id}>
              <button
                type="button"
                onClick={() => setProductId(product.id)}
                className="flex w-full cursor-pointer items-baseline justify-between gap-4 px-4 py-2.5 text-left hover:bg-sunken"
              >
                <span className="min-w-0 truncate text-small font-medium">{product.name}</span>
                <span className="shrink-0 font-mono text-hint text-ink-tertiary">
                  {product.scale_codes.join(" · ")} · {product.variant_count} Ausf.
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <ProductVariants productId={productId} onChoose={onChoose} onBack={() => setProductId(null)} />
      )}
    </div>
  );
}

function ProductVariants({
  productId,
  onChoose,
  onBack,
}: {
  productId: string;
  onChoose: (variant: ChosenVariant) => void;
  onBack: () => void;
}) {
  const product = useProduct(productId);
  const references = useReferences();
  const finishName = (code: string) => references.data?.finishes.find((finish) => finish.code === code)?.name ?? code;

  if (product.isPending) {
    return <p className="text-small text-ink-secondary">Die Ausführungen werden geladen …</p>;
  }
  if (product.isError) {
    return <p className="text-small text-danger">{errorMessage(product.error)}</p>;
  }
  const variants = product.data.scales.flatMap((scale) =>
    scale.variants.map((variant) => ({ scale: scale.scale_code, variant })),
  );
  return (
    <div className="rounded-sm border border-line">
      <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
        <p className="truncate text-small font-medium">{product.data.name}</p>
        <Button type="button" size="sm" variant="ghost" onClick={onBack}>
          Andere Suche
        </Button>
      </div>
      {variants.length === 0 ? <p className="px-4 py-3 text-small text-ink-secondary">Noch keine Ausführung angelegt.</p> : null}
      <ul className="divide-y divide-line">
        {variants.map(({ scale, variant }) => {
          const title = `${product.data.name} · ${scale} · ${finishName(variant.finish_code)}`;
          return (
            <li key={variant.id}>
              <button
                type="button"
                onClick={() => onChoose({ variantId: variant.id, title, sku: variant.sku })}
                className={cn(
                  "grid w-full cursor-pointer grid-cols-[3.5rem_minmax(0,1fr)_auto] items-baseline gap-3 px-4 py-2.5 text-left hover:bg-sunken",
                  !variant.active && "text-ink-tertiary",
                )}
              >
                <span className="font-mono text-small font-medium">{scale}</span>
                <span className="min-w-0">
                  <span className="block truncate text-small">{finishName(variant.finish_code)}</span>
                  <span className="block font-mono text-hint text-ink-tertiary">
                    {variant.sku}
                    {variant.allow_backorder ? " · auf Bestellung" : ""}
                    {variant.active ? "" : " · inaktiv"}
                  </span>
                </span>
                <span className="text-small tabular-nums">{formatPrice(variant.price_cents)}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function PrintNewLabels({ units, variant, onClose }: { units: UnitOut[]; variant: ChosenVariant; onClose: () => void }) {
  const stored = units[0]?.location?.code;
  return (
    <>
      <DialogTitle>{units.length === 1 ? "1 Einheit erfasst" : `${units.length} Einheiten erfasst`}</DialogTitle>
      <DialogDescription>
        {variant.title}. {stored ? `Liegen in ${stored}.` : "Liegen bereit zum Einlagern: Platz scannen, dann die Etiketten."}
      </DialogDescription>
      <ul className="mt-5 flex flex-wrap gap-1.5">
        {units.slice(0, 12).map((unit) => (
          <li key={unit.id} className="rounded-xs bg-sunken px-2 py-1 font-mono text-hint">
            {formatUnitCode(unit.code)}
          </li>
        ))}
        {units.length > 12 ? <li className="px-2 py-1 text-hint text-ink-tertiary">+ {units.length - 12}</li> : null}
      </ul>
      <LabelPrinter unitCodes={units.map((unit) => unit.code)} className="mt-6 border-t border-line pt-6" />
      <div className="mt-6 flex justify-end">
        <Button type="button" variant="secondary" onClick={onClose}>
          Fertig
        </Button>
      </div>
    </>
  );
}
