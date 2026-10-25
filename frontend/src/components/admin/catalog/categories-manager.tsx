"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { Panel } from "@/components/admin/panel";
import { FormError } from "@/components/forms/form-error";
import { SubmitButton } from "@/components/forms/submit-button";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { PendingNotice } from "@/components/ui/pending-notice";
import { Select } from "@/components/ui/select";
import { createCategory, updateCategory } from "@/lib/api/generated/admin-catalog/admin-catalog";
import type { CategoryOut, CategoryPatchIn } from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";
import { errorMessage, fieldErrorMessage } from "@/lib/i18n/problems";

import { categoryOptions } from "./product-details-form";
import { CATEGORIES_KEY, useCategories } from "./use-product";

function problemText(error: ApiProblem | null): string | undefined {
  if (error === null) {
    return undefined;
  }
  const field = error.fieldErrors[0];
  return field ? fieldErrorMessage(field.field, field.code) : errorMessage(error);
}

/** The category tree of the shop: create, rename, move. A category includes its subcategories. */
export function CategoriesManager() {
  const categories = useCategories();
  return (
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <Panel title="Kategorien" code="KAT 03">
        {categories.isPending ? (
          <PendingNotice>Kategorien werden geladen …</PendingNotice>
        ) : categories.isError ? (
          <p role="alert" className="text-small text-danger">
            {errorMessage(categories.error)}
          </p>
        ) : categories.data.length === 0 ? (
          <p className="text-small text-ink-secondary">Noch keine Kategorie. Lege rechts die erste an.</p>
        ) : (
          <ul className="divide-y divide-line">
            {categoryOptions(categories.data).map(({ category, depth }) => (
              <CategoryRow key={category.id} category={category} depth={depth} all={categories.data} />
            ))}
          </ul>
        )}
      </Panel>
      <NewCategoryForm categories={categories.data ?? []} />
    </div>
  );
}

function CategoryRow({ category, depth, all }: { category: CategoryOut; depth: number; all: readonly CategoryOut[] }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(category.name);
  const [parent, setParent] = useState(category.parent_id ?? "");
  const update = useMutation<CategoryOut, ApiProblem, CategoryPatchIn>({
    mutationFn: (patch) => updateCategory(category.id, patch),
    onSuccess() {
      setEditing(false);
      void queryClient.invalidateQueries({ queryKey: CATEGORIES_KEY });
    },
  });

  if (!editing) {
    return (
      <li className="flex items-center justify-between gap-4 py-3" style={{ paddingLeft: `${depth * 1.5}rem` }}>
        <span className="min-w-0">
          <span className="block font-medium">{category.name}</span>
          <span className="block font-mono text-hint text-ink-tertiary">/katalog/…/{category.slug}</span>
        </span>
        <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(true)}>
          Bearbeiten
        </Button>
      </li>
    );
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    update.mutate({ name: name.trim(), parent_id: parent || null });
  }

  return (
    <li className="py-3">
      <form noValidate onSubmit={onSubmit} className="flex flex-wrap items-end gap-3">
        <label className="min-w-48 flex-1">
          <span className="block text-hint text-ink-tertiary">Name</span>
          <Input value={name} maxLength={60} onChange={(event) => setName(event.target.value)} className="mt-1" />
        </label>
        <label className="w-56">
          <span className="block text-hint text-ink-tertiary">Liegt unter</span>
          <Select value={parent} onChange={(event) => setParent(event.target.value)} className="mt-1">
            <option value="">oberste Ebene</option>
            {categoryOptions(all)
              .filter(({ category: option }) => option.id !== category.id)
              .map(({ category: option, depth: level }) => (
                <option key={option.id} value={option.id}>
                  {`${" ".repeat(level)}${option.name}`}
                </option>
              ))}
          </Select>
        </label>
        <Button type="submit" size="sm" disabled={update.isPending}>
          Speichern
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(false)}>
          Abbrechen
        </Button>
        <p role="alert" className="w-full text-hint text-danger empty:hidden">
          {problemText(update.error)}
        </p>
      </form>
    </li>
  );
}

function NewCategoryForm({ categories }: { categories: readonly CategoryOut[] }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [parent, setParent] = useState("");
  const create = useMutation<CategoryOut, ApiProblem, void>({
    mutationFn: () => createCategory({ name: name.trim(), parent_id: parent || null }),
    onSuccess() {
      setName("");
      void queryClient.invalidateQueries({ queryKey: CATEGORIES_KEY });
    },
  });

  return (
    <Panel title="Neue Kategorie" code="KAT 04">
      <form
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          if (name.trim()) {
            create.mutate();
          }
        }}
        className="space-y-4"
      >
        <FormError message={problemText(create.error)} />
        <FormField label="Name" hint="Die Adresse entsteht daraus, z. B. „Gebäude“ → gebaeude.">
          {(control) => (
            <Input {...control} value={name} maxLength={60} onChange={(event) => setName(event.target.value)} />
          )}
        </FormField>
        <FormField label="Liegt unter">
          {(control) => (
            <Select {...control} value={parent} onChange={(event) => setParent(event.target.value)}>
              <option value="">oberste Ebene</option>
              {categoryOptions(categories).map(({ category, depth }) => (
                <option key={category.id} value={category.id}>
                  {`${" ".repeat(depth)}${category.name}`}
                </option>
              ))}
            </Select>
          )}
        </FormField>
        <SubmitButton pending={create.isPending} pendingLabel="Legt an …" disabled={!name.trim()}>
          Kategorie anlegen
        </SubmitButton>
      </form>
    </Panel>
  );
}
