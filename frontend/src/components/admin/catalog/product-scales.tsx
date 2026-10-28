"use client";

import { useState, type FormEvent } from "react";

import { Panel } from "@/components/admin/panel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { SpecLine } from "@/components/ui/spec-line";
import {
  addProductScale,
  addVariant,
  deleteProductScale,
  deleteVariant,
  updateProductScale,
  updateVariant,
} from "@/lib/api/generated/admin-catalog/admin-catalog";
import type {
  FinishOut,
  ProductOut,
  ProductScaleOut,
  ReferencesOut,
  ScaleOut,
  VariantOut,
} from "@/lib/api/generated/model";
import { centsToEuroInput, scaleSpec } from "@/lib/catalog/format";
import { scaleLabel } from "@/lib/catalog/scales";
import { ifMatch } from "@/lib/catalog/versions";
import { errorMessage, fieldErrorMessage } from "@/lib/i18n/problems";
import {
  DEFAULT_LEAD_TIME,
  euroPrice,
  leadTimeSchema,
  optionalEuroPrice,
  optionalGrams,
  optionalMillimetres,
} from "@/lib/validation/catalog";

import { useProductCommand } from "./use-product";

type Props = { product: ProductOut; references: ReferencesOut };

/** The scales of a product, each with its dimensions and the variants sold in it. */
export function ProductScales({ product, references }: Props) {
  const command = useProductCommand(product.id);
  const offered = new Set(product.scales.map((s) => s.scale_code));
  const missing = references.scales.filter((scale) => !offered.has(scale.code));
  const ordered = references.scales.flatMap((scale) => {
    const productScale = product.scales.find((s) => s.scale_code === scale.code);
    return productScale ? [{ scale, productScale }] : [];
  });

  return (
    <Panel title="Maßstäbe und Varianten" code="PRD 03">
      {ordered.length === 0 ? (
        <p className="text-small text-ink-secondary">
          Noch kein Maßstab. Wähle unten, in welchen Maßstäben es das Modell gibt.
        </p>
      ) : (
        <div className="space-y-6">
          {ordered.map(({ scale, productScale }) => (
            <ScaleBlock
              key={productScale.id}
              product={product}
              scale={scale}
              productScale={productScale}
              finishes={references.finishes}
            />
          ))}
        </div>
      )}
      {missing.length > 0 ? (
        <div className="mt-6 border-t border-line pt-5">
          <p className="label-caps text-ink-tertiary">Maßstab hinzufügen</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {missing.map((scale) => (
              <Button
                key={scale.code}
                type="button"
                variant="secondary"
                size="sm"
                disabled={command.isPending}
                onClick={() =>
                  command.mutate(() =>
                    addProductScale(product.id, { scale_code: scale.code }, ifMatch(product.version)),
                  )
                }
              >
                + {scaleLabel(scale)}
              </Button>
            ))}
          </div>
          <p role="alert" className="mt-2 text-hint text-danger">
            {command.isError ? errorMessage(command.error) : null}
          </p>
        </div>
      ) : null}
    </Panel>
  );
}

type ScaleBlockProps = {
  product: ProductOut;
  scale: ScaleOut;
  productScale: ProductScaleOut;
  finishes: readonly FinishOut[];
};

function ScaleBlock({ product, scale, productScale, finishes }: ScaleBlockProps) {
  const remove = useProductCommand(product.id);
  const offeredFinishes = new Set(productScale.variants.map((v) => v.finish_code));
  const variants = finishes.flatMap((finish) => {
    const variant = productScale.variants.find((v) => v.finish_code === finish.code);
    return variant ? [{ finish, variant }] : [];
  });

  return (
    <section aria-label={`Maßstab ${scaleLabel(scale)}`} className="rounded-md border border-line">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-line bg-stage px-4 py-3">
        <div className="flex items-baseline gap-4">
          <span className="text-heading font-extralight">{scale.name}</span>
          <SpecLine values={scaleSpec(scale).slice(1)} size="small" />
        </div>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={remove.isPending}
          onClick={() => {
            if (window.confirm(`Maßstab ${scaleLabel(scale)} mit allen Varianten entfernen?`)) {
              remove.mutate(() => deleteProductScale(productScale.id, ifMatch(product.version)));
            }
          }}
        >
          Maßstab entfernen
        </Button>
      </header>
      <div className="space-y-5 p-4">
        <p role="alert" className="text-hint text-danger empty:hidden">
          {remove.isError ? errorMessage(remove.error) : null}
        </p>
        <DimensionsForm product={product} productScale={productScale} />
        {variants.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[40rem] text-small">
              <caption className="sr-only">Varianten in {scale.name}</caption>
              <thead>
                <tr className="text-left text-hint text-ink-tertiary">
                  <th scope="col" className="pb-2 font-medium">Ausführung</th>
                  <th scope="col" className="pb-2 font-medium">SKU · EAN</th>
                  <th scope="col" className="pb-2 font-medium">Preis €</th>
                  <th scope="col" className="pb-2 font-medium">Früher €</th>
                  <th scope="col" className="pb-2 font-medium">Im Shop</th>
                  <th scope="col" className="pb-2 font-medium">Auf Bestellung</th>
                  <th scope="col" className="pb-2"><span className="sr-only">Aktionen</span></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {variants.map(({ finish, variant }) => (
                  <VariantRow key={variant.id} product={product} finish={finish} variant={variant} />
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-small text-ink-secondary">Noch keine Variante in {scale.name}.</p>
        )}
        {offeredFinishes.size < finishes.length ? (
          <NewVariantForm
            product={product}
            productScale={productScale}
            finishes={finishes.filter((f) => !offeredFinishes.has(f.code))}
          />
        ) : null}
      </div>
    </section>
  );
}

function asText(value: number | null): string {
  return value === null ? "" : String(value).replace(".", ",");
}

function DimensionsForm({ product, productScale }: { product: ProductOut; productScale: ProductScaleOut }) {
  const command = useProductCommand(product.id);
  const [values, setValues] = useState(() => ({
    length_mm: asText(productScale.length_mm),
    width_mm: asText(productScale.width_mm),
    height_mm: asText(productScale.height_mm),
    weight_g: asText(productScale.weight_g),
  }));
  const [error, setError] = useState<string | null>(null);

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsed = {
      length_mm: optionalMillimetres.safeParse(values.length_mm),
      width_mm: optionalMillimetres.safeParse(values.width_mm),
      height_mm: optionalMillimetres.safeParse(values.height_mm),
      weight_g: optionalGrams.safeParse(values.weight_g),
    };
    const failed = Object.values(parsed).find((result) => !result.success);
    if (failed && !failed.success) {
      setError(failed.error.issues[0]?.message ?? "Bitte prüfe die Maße.");
      return;
    }
    setError(null);
    command.mutate(() =>
      updateProductScale(
        productScale.id,
        {
          length_mm: parsed.length_mm.data ?? null,
          width_mm: parsed.width_mm.data ?? null,
          height_mm: parsed.height_mm.data ?? null,
          weight_g: parsed.weight_g.data ?? null,
        },
        ifMatch(product.version),
      ),
    );
  }

  const fields = [
    ["length_mm", "Länge mm"],
    ["width_mm", "Breite mm"],
    ["height_mm", "Höhe mm"],
    ["weight_g", "Gewicht g"],
  ] as const;
  return (
    <form noValidate onSubmit={onSubmit} className="flex flex-wrap items-end gap-3">
      {fields.map(([name, label]) => (
        <label key={name} className="w-28">
          <span className="block text-hint text-ink-tertiary">{label}</span>
          <Input
            inputMode="decimal"
            value={values[name]}
            onChange={(event) => setValues({ ...values, [name]: event.target.value })}
            className="mt-1"
          />
        </label>
      ))}
      <Button type="submit" variant="secondary" size="sm" disabled={command.isPending}>
        {command.isPending ? "Speichert …" : "Maße speichern"}
      </Button>
      <p role="alert" className="w-full text-hint text-danger empty:hidden">
        {error ?? (command.isError ? errorMessage(command.error) : null)}
      </p>
    </form>
  );
}

function VariantRow({ product, finish, variant }: { product: ProductOut; finish: FinishOut; variant: VariantOut }) {
  const command = useProductCommand(product.id);
  const [price, setPrice] = useState(centsToEuroInput(variant.price_cents));
  const [former, setFormer] = useState(
    variant.compare_at_price_cents === null ? "" : centsToEuroInput(variant.compare_at_price_cents),
  );
  const [error, setError] = useState<string | null>(null);
  const [leadMin, setLeadMin] = useState(String(variant.lead_time_min_weeks ?? DEFAULT_LEAD_TIME[0]));
  const [leadMax, setLeadMax] = useState(String(variant.lead_time_max_weeks ?? DEFAULT_LEAD_TIME[1]));
  const fieldError = command.error?.fieldErrors[0];

  function saveLeadTime() {
    const parsed = leadTimeSchema.safeParse({ min: leadMin, max: leadMax });
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? null);
      return;
    }
    setError(null);
    const { min, max } = parsed.data;
    if (min === variant.lead_time_min_weeks && max === variant.lead_time_max_weeks) {
      return;
    }
    command.mutate(() =>
      updateVariant(variant.id, { lead_time_min_weeks: min, lead_time_max_weeks: max }, ifMatch(product.version)),
    );
  }

  function savePrices() {
    const parsedPrice = euroPrice.safeParse(price);
    const parsedFormer = optionalEuroPrice.safeParse(former);
    if (!parsedPrice.success || !parsedFormer.success) {
      setError((parsedPrice.error ?? parsedFormer.error)?.issues[0]?.message ?? null);
      return;
    }
    setError(null);
    if (parsedPrice.data === variant.price_cents && parsedFormer.data === variant.compare_at_price_cents) {
      return;
    }
    command.mutate(() =>
      updateVariant(
        variant.id,
        { price_cents: parsedPrice.data, compare_at_price_cents: parsedFormer.data },
        ifMatch(product.version),
      ),
    );
  }

  const message =
    error ??
    (fieldError ? fieldErrorMessage(fieldError.field, fieldError.code) : command.isError ? errorMessage(command.error) : null);
  return (
    <>
      <tr>
        <th scope="row" className="py-2 pr-3 text-left font-medium">
          {finish.name}
        </th>
        <td className="py-2 pr-3 font-mono text-hint text-ink-secondary">
          <span className="block">{variant.sku}</span>
          <span className="block text-ink-tertiary">{variant.gtin}</span>
        </td>
        <td className="py-2 pr-3">
          <Input
            aria-label={`Preis ${finish.name} in Euro`}
            inputMode="decimal"
            value={price}
            onChange={(event) => setPrice(event.target.value)}
            onBlur={savePrices}
            className="w-24"
          />
        </td>
        <td className="py-2 pr-3">
          <Input
            aria-label={`Früherer Preis ${finish.name} in Euro`}
            inputMode="decimal"
            value={former}
            placeholder="–"
            onChange={(event) => setFormer(event.target.value)}
            onBlur={savePrices}
            className="w-24"
          />
        </td>
        <td className="py-2 pr-3">
          <input
            type="checkbox"
            aria-label={`${finish.name} im Shop anbieten`}
            checked={variant.active}
            disabled={command.isPending}
            onChange={(event) =>
              command.mutate(() =>
                updateVariant(variant.id, { active: event.target.checked }, ifMatch(product.version)),
              )
            }
            className="size-4 cursor-pointer accent-selected"
          />
        </td>
        <td className="py-2 pr-3">
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              aria-label={`${finish.name} auf Bestellung fertigen (auch ohne Lagerbestand bestellbar)`}
              checked={variant.allow_backorder}
              disabled={command.isPending}
              onChange={(event) =>
                command.mutate(() =>
                  updateVariant(variant.id, { allow_backorder: event.target.checked }, ifMatch(product.version)),
                )
              }
              className="size-4 cursor-pointer accent-selected"
            />
            {variant.allow_backorder ? (
              <span className="flex items-center gap-1 text-hint text-ink-secondary">
                <Input
                  aria-label={`Lieferzeit ${finish.name}: frühestens nach Wochen`}
                  inputMode="numeric"
                  value={leadMin}
                  onChange={(event) => setLeadMin(event.target.value)}
                  onBlur={saveLeadTime}
                  className="w-11 px-2 text-center werkstatt:h-8"
                />
                <span aria-hidden="true">–</span>
                <Input
                  aria-label={`Lieferzeit ${finish.name}: spätestens nach Wochen`}
                  inputMode="numeric"
                  value={leadMax}
                  onChange={(event) => setLeadMax(event.target.value)}
                  onBlur={saveLeadTime}
                  className="w-11 px-2 text-center werkstatt:h-8"
                />
                <span>Wo.</span>
              </span>
            ) : null}
          </div>
        </td>
        <td className="py-2 text-right">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={command.isPending}
            onClick={() => {
              if (window.confirm(`Variante ${variant.sku} entfernen?`)) {
                command.mutate(() => deleteVariant(variant.id, ifMatch(product.version)));
              }
            }}
          >
            Entfernen
          </Button>
        </td>
      </tr>
      {message ? (
        <tr>
          <td colSpan={7} className="pb-2">
            <p role="alert" className="text-hint text-danger">
              {message}
            </p>
          </td>
        </tr>
      ) : null}
    </>
  );
}

function NewVariantForm({
  product,
  productScale,
  finishes,
}: {
  product: ProductOut;
  productScale: ProductScaleOut;
  finishes: readonly FinishOut[];
}) {
  const command = useProductCommand(product.id);
  const [finish, setFinish] = useState(finishes[0]?.code ?? "");
  const [price, setPrice] = useState("");
  const [error, setError] = useState<string | null>(null);

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsed = euroPrice.safeParse(price);
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? null);
      return;
    }
    setError(null);
    command.mutate(
      () => addVariant(productScale.id, { finish_code: finish, price_cents: parsed.data }, ifMatch(product.version)),
      { onSuccess: () => setPrice("") },
    );
  }

  return (
    <form noValidate onSubmit={onSubmit} className="flex flex-wrap items-end gap-3 border-t border-line pt-4">
      <label className="w-44">
        <span className="block text-hint text-ink-tertiary">Neue Ausführung</span>
        <Select value={finish} onChange={(event) => setFinish(event.target.value)} className="mt-1">
          {finishes.map((option) => (
            <option key={option.code} value={option.code}>
              {option.name}
            </option>
          ))}
        </Select>
      </label>
      <label className="w-28">
        <span className="block text-hint text-ink-tertiary">Preis €</span>
        <Input inputMode="decimal" value={price} onChange={(event) => setPrice(event.target.value)} placeholder="49,90" className="mt-1" />
      </label>
      <Button type="submit" size="sm" disabled={command.isPending}>
        {command.isPending ? "Legt an …" : "Variante anlegen"}
      </Button>
      <p role="alert" className="w-full text-hint text-danger empty:hidden">
        {error ?? (command.isError ? errorMessage(command.error) : null)}
      </p>
    </form>
  );
}
