"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect } from "react";
import { Controller, useForm, useWatch } from "react-hook-form";

import { Panel } from "@/components/admin/panel";
import { FormError } from "@/components/forms/form-error";
import { SubmitButton } from "@/components/forms/submit-button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { updateProduct } from "@/lib/api/generated/admin-catalog/admin-catalog";
import type { CategoryOut, EpochOut, ProductOut, ProductPatchIn } from "@/lib/api/generated/model";
import { ifMatch } from "@/lib/catalog/versions";
import { applyProblemToForm } from "@/lib/forms/apply-problem";
import { productDetailsSchema, type ProductDetailsValues } from "@/lib/validation/catalog";
import { cn } from "@/lib/utils";

import { useProductCommand } from "./use-product";

function valuesOf(product: ProductOut): ProductDetailsValues {
  return {
    name: product.name,
    slug: product.slug,
    summary: product.summary,
    description: product.description,
    prototype: product.prototype,
    primary_category_id: product.primary_category_id ?? "",
    epoch_codes: product.epoch_codes,
  };
}

/** Categories in tree order, with their depth for indenting the options. */
export function categoryOptions(categories: readonly CategoryOut[]): { category: CategoryOut; depth: number }[] {
  const children = new Map<string | null, CategoryOut[]>();
  for (const category of categories) {
    const siblings = children.get(category.parent_id) ?? [];
    siblings.push(category);
    children.set(category.parent_id, siblings);
  }
  const ordered: { category: CategoryOut; depth: number }[] = [];
  const visit = (parent: string | null, depth: number) => {
    const level = [...(children.get(parent) ?? [])].sort(
      (a, b) => a.position - b.position || a.name.localeCompare(b.name, "de"),
    );
    for (const category of level) {
      ordered.push({ category, depth });
      visit(category.id, depth + 1);
    }
  };
  visit(null, 0);
  return ordered;
}

type ProductDetailsFormProps = {
  product: ProductOut;
  categories: readonly CategoryOut[];
  epochs: readonly EpochOut[];
};

/** Texts, address, category and epochs. Sends only what changed, with If-Match. */
export function ProductDetailsForm({ product, categories, epochs }: ProductDetailsFormProps) {
  const command = useProductCommand(product.id);
  const form = useForm<ProductDetailsValues>({
    resolver: zodResolver(productDetailsSchema),
    defaultValues: valuesOf(product),
    mode: "onTouched",
  });
  const {
    register,
    control,
    formState: { errors, isDirty, isSubmitting, dirtyFields },
  } = form;
  const slugLocked = product.published_at !== null;
  const slug = useWatch({ control, name: "slug" });

  // A newer state from elsewhere (another section, another person) replaces the form,
  // unless there are unsaved edits; those win and are checked by If-Match on saving.
  useEffect(() => {
    if (!form.formState.isDirty) {
      form.reset(valuesOf(product));
    }
  }, [product, form]);

  const onSubmit = form.handleSubmit(async (values) => {
    const patch: ProductPatchIn = {};
    if (dirtyFields.name) patch.name = values.name;
    if (dirtyFields.slug && !slugLocked) patch.slug = values.slug;
    if (dirtyFields.summary) patch.summary = values.summary;
    if (dirtyFields.description) patch.description = values.description;
    if (dirtyFields.prototype) patch.prototype = values.prototype;
    if (dirtyFields.primary_category_id) patch.primary_category_id = values.primary_category_id || null;
    if (dirtyFields.epoch_codes) patch.epoch_codes = values.epoch_codes;
    try {
      const saved = await command.mutateAsync(() => updateProduct(product.id, patch, ifMatch(product.version)));
      form.reset(valuesOf(saved));
    } catch (error) {
      applyProblemToForm(error, form.setError, {
        fields: ["name", "slug", "summary", "description", "prototype", "primary_category_id", "epoch_codes"],
        codeFields: { slug_taken: "slug", slug_locked: "slug" },
      });
    }
  });
  const formError = errors.root?.server?.message;

  return (
    <Panel title="Stammdaten" code="PRD 02">
      <form noValidate onSubmit={onSubmit} className="space-y-5">
        <FormError message={formError} />
        <FormField label="Name" error={errors.name?.message}>
          {(field) => <Input {...field} {...register("name")} maxLength={120} />}
        </FormField>
        <FormField
          label="Adresse im Shop"
          hint={
            slugLocked
              ? "Fest, seit das Produkt veröffentlicht wurde: Links zeigen darauf."
              : `/produkte/${slug || "…"}`
          }
          error={errors.slug?.message}
        >
          {(field) => (
            <Input {...field} {...register("slug")} readOnly={slugLocked} className={cn(slugLocked && "bg-sunken")} />
          )}
        </FormField>
        <FormField label="Kurztext" hint="Ein Satz für Karten und Suchmaschinen." error={errors.summary?.message}>
          {(field) => <Input {...field} {...register("summary")} />}
        </FormField>
        <FormField label="Beschreibung" hint="Leerzeilen trennen Absätze." error={errors.description?.message}>
          {(field) => <Textarea {...field} {...register("description")} rows={7} />}
        </FormField>
        <div className="grid gap-5 sm:grid-cols-2">
          <FormField label="Vorbild" hint="z. B. Altenau (Harz), Deutsche Reichsbahn" error={errors.prototype?.message}>
            {(field) => <Input {...field} {...register("prototype")} />}
          </FormField>
          <FormField label="Kategorie" error={errors.primary_category_id?.message}>
            {(field) => (
              <Select {...field} {...register("primary_category_id")}>
                <option value="">Keine Kategorie</option>
                {categoryOptions(categories).map(({ category, depth }) => (
                  <option key={category.id} value={category.id}>
                    {`${" ".repeat(depth)}${category.name}`}
                  </option>
                ))}
              </Select>
            )}
          </FormField>
        </div>
        <fieldset>
          <legend className="text-small font-medium">Epochen</legend>
          <Controller
            control={control}
            name="epoch_codes"
            render={({ field }) => (
              <div className="mt-2 flex flex-wrap gap-2">
                {epochs.map((epoch) => {
                  const checked = field.value.includes(epoch.code);
                  return (
                    <label
                      key={epoch.code}
                      className={cn(
                        "inline-flex h-9 cursor-pointer items-center gap-2 rounded-full border px-4 text-sm font-medium",
                        "has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-focus",
                        checked ? "border-selected bg-selected text-on-selected" : "border-line-strong hover:border-ink",
                      )}
                    >
                      <input
                        type="checkbox"
                        className="sr-only"
                        checked={checked}
                        onChange={() =>
                          field.onChange(
                            checked
                              ? field.value.filter((code) => code !== epoch.code)
                              : [...field.value, epoch.code],
                          )
                        }
                      />
                      {epoch.code}
                      <span className={cn("font-normal", checked ? "text-on-selected" : "text-ink-tertiary")}>
                        {epoch.period}
                      </span>
                    </label>
                  );
                })}
              </div>
            )}
          />
        </fieldset>
        <div className="flex items-center gap-4">
          <SubmitButton pending={isSubmitting} pendingLabel="Speichert …" disabled={!isDirty}>
            Stammdaten speichern
          </SubmitButton>
          {isDirty ? <p className="text-hint text-ink-tertiary">Ungespeicherte Änderungen</p> : null}
        </div>
      </form>
    </Panel>
  );
}
