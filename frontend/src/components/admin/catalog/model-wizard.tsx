"use client";

import { useQueryClient } from "@tanstack/react-query";
import type { Route } from "next";
import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { LabelPrinter } from "@/components/admin/inventory/label-printer";
import { usePlaces } from "@/components/admin/inventory/stock-dialogs";
import { Button } from "@/components/ui/button";
import { ColorDot } from "@/components/ui/color-dot";
import { Input } from "@/components/ui/input";
import { OptionGroup, OptionPill } from "@/components/ui/option-pill";
import { PendingNotice } from "@/components/ui/pending-notice";
import { Select } from "@/components/ui/select";
import { attachProductImage, createQuickEntry, publishProduct } from "@/lib/api/generated/admin-catalog/admin-catalog";
import { labelUnits } from "@/lib/api/generated/admin-inventory/admin-inventory";
import type { FinishOut, ProductOut } from "@/lib/api/generated/model";
import { isApiProblem } from "@/lib/api/problem";
import { finishLabel } from "@/lib/catalog/format";
import { scaleLabel } from "@/lib/catalog/scales";
import { ifMatch } from "@/lib/catalog/versions";
import { errorMessage, fieldErrorMessage } from "@/lib/i18n/problems";
import { IMAGE_PICKER_ACCEPT, uploadImage } from "@/lib/media/upload";
import { colorName, euroPrice } from "@/lib/validation/catalog";

import { categoryOptions } from "./product-details-form";
import { ADMIN_PRODUCTS_KEY, productQueryKey, useCategories, useReferences } from "./use-product";

type Photo = { key: string; previewUrl: string; assetId: string | null; error: string | null };

/** What step 2 asks per finish: chosen or not, its price, and (if painted) its colours. */
type FinishChoice = { chosen: boolean; price: string; colors: string[]; draft: string };

/** An Ausführung the wizard made; ``key`` is what step 2 planned (scale, finish, colour). */
type Made = { key: string; variantId: string; label: string; sku: string; colored: boolean };

const STEPS = ["Name und Fotos", "Ausführungen und Preis", "Bestand", "Etiketten und Shop"] as const;

const PLACE_KEY = "mb-einbuchen-platz";

function rememberedPlace(): string {
  try {
    return window.localStorage.getItem(PLACE_KEY) ?? "";
  } catch {
    return "";
  }
}

function failure(error: unknown): string {
  const field = isApiProblem(error) ? error.fieldErrors[0] : undefined;
  return field ? fieldErrorMessage(field.field, field.code) : errorMessage(error);
}

function plannedKey(scaleCode: string, entry: { finish: FinishOut; color: string }): string {
  return `${scaleCode}|${entry.finish.code}|${entry.color}`;
}

/** What step 2 makes: one Ausführung per finish, or per colour of a painted one. */
export function plannedVariants(
  finishes: readonly FinishOut[],
  choices: Readonly<Record<string, FinishChoice>>,
): { finish: FinishOut; color: string; price: string }[] {
  return finishes.flatMap((finish) => {
    const choice = choices[finish.code];
    if (!choice?.chosen) {
      return [];
    }
    const colors = finish.colored && choice.colors.length > 0 ? choice.colors : [""];
    return colors.map((color) => ({ finish, color, price: choice.price }));
  });
}

/**
 * Neues Modell, in four steps that fit a phone: name and photos; scale, finishes,
 * colours and price; how many pieces lie where (may be skipped); labels and whether it
 * shows in the shop. It ends on the model's page. Built from the catalogue's quick entry
 * (one call per Ausführung), the gallery and the store (ADR 0028).
 */
export function ModelWizard() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const references = useReferences();
  const categories = useCategories();
  const places = usePlaces();
  const [step, setStep] = useState(0);
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  // Step 1
  const [name, setName] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [photos, setPhotos] = useState<Photo[]>([]);
  // Step 2
  const [scaleCode, setScaleCode] = useState("");
  const [choices, setChoices] = useState<Record<string, FinishChoice>>({});
  // After step 2: what exists
  // Kept after every call that worked, so a retry after a failure makes nothing twice.
  const [product, setProduct] = useState<ProductOut | null>(null);
  const [made, setMade] = useState<Made[]>([]);
  const [attached, setAttached] = useState<string[]>([]);
  // Step 3
  const [counts, setCounts] = useState<Record<string, { quantity: string; place: string }>>({});
  const [booked, setBooked] = useState<Record<string, number>>({});
  // Step 4
  const [show, setShow] = useState(true);

  useEffect(
    () => () => {
      photos.forEach((photo) => URL.revokeObjectURL(photo.previewUrl));
    },
    // Only on leaving the page: the previews stay while the wizard runs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  if (references.isPending || categories.isPending) {
    return <PendingNotice>Wird geladen …</PendingNotice>;
  }
  if (references.isError || categories.isError) {
    return <p className="text-small text-danger">{errorMessage(references.error ?? categories.error)}</p>;
  }
  const finishes = references.data.finishes.filter((finish) => finish.offered);
  const planned = plannedVariants(finishes, choices);

  function addPhotos(files: FileList | null) {
    for (const file of Array.from(files ?? [])) {
      const key = crypto.randomUUID();
      const previewUrl = URL.createObjectURL(file);
      setPhotos((before) => [...before, { key, previewUrl, assetId: null, error: null }]);
      const update = (patch: Partial<Photo>) =>
        setPhotos((before) => before.map((photo) => (photo.key === key ? { ...photo, ...patch } : photo)));
      uploadImage(file)
        .then((asset) => update({ assetId: asset.id }))
        .catch((error: unknown) => update({ error: isApiProblem(error) ? errorMessage(error) : "Das Foto ließ sich nicht hochladen." }));
    }
  }

  function choose(code: string, change: Partial<FinishChoice>) {
    setChoices((before) => ({
      ...before,
      [code]: { ...(before[code] ?? { chosen: false, price: "", colors: [], draft: "" }), ...change },
    }));
  }

  async function run(action: () => Promise<void>) {
    setPending(true);
    setProblem(null);
    try {
      await action();
    } catch (error) {
      setProblem(failure(error));
    } finally {
      setPending(false);
    }
  }

  /** Step 2 done: the model and its Ausführungen come into being, with the photos. */
  async function create() {
    if (!scaleCode || planned.length === 0) {
      setProblem("Bitte Maßstab und mindestens eine Ausführung wählen.");
      return;
    }
    const prices = planned.map((entry) => euroPrice.safeParse(entry.price));
    const wrong = prices.find((price) => !price.success);
    if (wrong && !wrong.success) {
      setProblem(wrong.error.issues[0]?.message ?? "Bitte einen Preis wie 49,90 eingeben.");
      return;
    }
    if (photos.some((photo) => photo.assetId === null && photo.error === null)) {
      setProblem("Die Fotos laden noch. Einen Moment, dann noch einmal.");
      return;
    }
    await run(async () => {
      const uploaded = photos.flatMap((photo) => (photo.assetId ? [photo.assetId] : []));
      let current: ProductOut | null = product;
      const created: Made[] = [...made];
      const withPhotos = [...attached];
      const keep = (next: ProductOut) => {
        current = next;
        setProduct(next);
        queryClient.setQueryData(productQueryKey(next.id), next);
      };
      try {
        for (const [index, entry] of planned.entries()) {
          const key = plannedKey(scaleCode, entry);
          if (created.some((done) => done.key === key)) {
            continue; // made before an earlier attempt failed
          }
          const price = prices[index];
          const first = current === null ? (uploaded[0] ?? null) : null;
          const answer = await createQuickEntry({
            product_id: current?.id ?? null,
            name: current ? null : name.trim(),
            category_id: current || categoryId === "" ? null : categoryId,
            scale_code: scaleCode,
            finish_code: entry.finish.code,
            color: entry.color,
            price_cents: price?.success ? price.data : 0,
            asset_id: first,
          });
          keep(answer.product);
          created.push({
            key,
            variantId: answer.variant.id,
            label: `${scaleCode} · ${finishLabel(entry.finish.name, entry.color)}`,
            sku: answer.variant.sku,
            colored: entry.color !== "",
          });
          setMade([...created]);
          if (first) {
            withPhotos.push(first);
            setAttached([...withPhotos]);
          }
        }
        for (const assetId of uploaded) {
          const model: ProductOut | null = current;
          if (model && !withPhotos.includes(assetId)) {
            keep(await attachProductImage(model.id, { asset_id: assetId }));
            withPhotos.push(assetId);
            setAttached([...withPhotos]);
          }
        }
      } finally {
        void queryClient.invalidateQueries({ queryKey: ADMIN_PRODUCTS_KEY });
      }
      const place = places.data?.some((item) => item.code === rememberedPlace()) ? rememberedPlace() : "";
      setCounts(Object.fromEntries(created.map((entry) => [entry.variantId, { quantity: "0", place }])));
      setShow(uploaded.length > 0 && prices.every((price) => price.success && price.data > 0));
      setStep(2);
    });
  }

  /** Step 3 done: the pieces counted are booked in where they lie. */
  async function bookIn() {
    const wanted = made.flatMap((entry) => {
      const count = counts[entry.variantId];
      const quantity = Number.parseInt(count?.quantity ?? "0", 10) || 0;
      return quantity > 0 ? [{ entry, quantity, place: count?.place ?? "" }] : [];
    });
    if (wanted.some((line) => line.place === "")) {
      setProblem("Bitte zu jeder Anzahl den Platz wählen, in dem die Stücke liegen.");
      return;
    }
    await run(async () => {
      const done: Record<string, number> = { ...booked };
      for (const line of wanted) {
        if (done[line.entry.variantId] !== undefined) {
          continue; // booked before an earlier attempt failed
        }
        const batch = await labelUnits({ variant_id: line.entry.variantId, quantity: line.quantity, location_code: line.place });
        done[line.entry.variantId] = batch.items.length;
        setBooked({ ...done });
        try {
          window.localStorage.setItem(PLACE_KEY, line.place);
        } catch {
          // The place just isn't remembered.
        }
      }
      setStep(3);
    });
  }

  /** Step 4 done: in the shop if wanted, then the model's page. */
  async function finish() {
    if (!product) {
      return;
    }
    await run(async () => {
      if (show && product.status !== "active") {
        const published = await publishProduct(product.id, ifMatch(product.version));
        queryClient.setQueryData(productQueryKey(product.id), published);
      }
      void queryClient.invalidateQueries({ queryKey: ADMIN_PRODUCTS_KEY });
      router.push(`/admin/modelle/${product.id}` as Route);
    });
  }

  const labels = made.map((entry) => ({ variantId: entry.variantId, quantity: booked[entry.variantId] ?? 0, sku: entry.sku }));
  const printable = labels.some((label) => label.quantity > 0) ? labels.filter((label) => label.quantity > 0) : labels.map((label) => ({ ...label, quantity: 1 }));

  return (
    <div className="mx-auto max-w-2xl">
      <p className="label-caps text-ink-tertiary">
        Schritt {step + 1} von {STEPS.length}
      </p>
      <h1 className="mt-2 text-heading">Neues Modell: {STEPS[step]}</h1>
      <ol aria-label="Schritte" className="mt-4 grid grid-cols-4 gap-1">
        {STEPS.map((label, index) => (
          <li key={label} aria-current={index === step ? "step" : undefined} className={index <= step ? "h-1 rounded-full bg-selected" : "h-1 rounded-full bg-line"}>
            <span className="sr-only">{label}</span>
          </li>
        ))}
      </ol>

      <div className="mt-8 space-y-6">
        {step === 0 ? (
          <>
            <Field label="Name" htmlFor="wizard-name">
              <Input id="wizard-name" value={name} onChange={(event) => setName(event.target.value)} maxLength={120} placeholder="z. B. IFA W50 Kipper" />
            </Field>
            <Field label="Kategorie" htmlFor="wizard-category" hint="Für den Shop nötig; später änderbar.">
              <Select id="wizard-category" value={categoryId} onChange={(event) => setCategoryId(event.target.value)}>
                <option value="">Später wählen</option>
                {categoryOptions(categories.data).map(({ category, depth }) => (
                  <option key={category.id} value={category.id}>
                    {" ".repeat(depth)}
                    {category.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Fotos" htmlFor="wizard-photos" hint="Das erste ist das Hauptbild.">
              <Input id="wizard-photos" type="file" accept={IMAGE_PICKER_ACCEPT} multiple onChange={(event) => addPhotos(event.target.files)} />
            </Field>
            {photos.length > 0 ? (
              <ul className="grid grid-cols-4 gap-2">
                {photos.map((photo) => (
                  <li key={photo.key} className="relative aspect-square overflow-hidden rounded-sm bg-stage">
                    {/* eslint-disable-next-line @next/next/no-img-element -- a local preview, not an asset */}
                    <img src={photo.previewUrl} alt="" className="size-full object-cover" />
                    <span className="absolute inset-x-0 bottom-0 bg-surface/90 px-1 text-center text-hint">
                      {photo.error ? <span className="text-danger">Fehler</span> : photo.assetId ? "fertig" : "lädt …"}
                    </span>
                  </li>
                ))}
              </ul>
            ) : null}
            <Actions>
              <Button type="button" disabled={name.trim() === ""} onClick={() => setStep(1)}>
                Weiter
              </Button>
            </Actions>
          </>
        ) : null}

        {step === 1 ? (
          <>
            <OptionGroup label="Maßstab" value={scaleCode} onValueChange={setScaleCode}>
              {references.data.scales.map((scale) => (
                <OptionPill key={scale.code} value={scale.code}>
                  {scaleLabel(scale)}
                </OptionPill>
              ))}
            </OptionGroup>
            <fieldset className="space-y-4">
              <legend className="label-caps text-ink-tertiary">Ausführungen</legend>
              {finishes.map((finish) => {
                const choice = choices[finish.code];
                return (
                  <div key={finish.code} className="rounded-md border border-line p-4">
                    <label className="flex cursor-pointer items-center gap-3 font-medium">
                      <input
                        type="checkbox"
                        checked={choice?.chosen ?? false}
                        onChange={(event) => choose(finish.code, { chosen: event.target.checked })}
                        className="size-5 accent-[var(--selected)]"
                      />
                      {finish.name}
                    </label>
                    {choice?.chosen ? (
                      <div className="mt-4 space-y-4">
                        <Field label={`Preis ${finish.name}`} htmlFor={`price-${finish.code}`}>
                          <Input
                            id={`price-${finish.code}`}
                            value={choice.price}
                            onChange={(event) => choose(finish.code, { price: event.target.value })}
                            inputMode="decimal"
                            placeholder="49,90"
                          />
                        </Field>
                        {finish.colored ? (
                          <div>
                            <p className="text-small font-medium">Farben</p>
                            {choice.colors.length > 0 ? (
                              <ul className="mt-2 flex flex-wrap gap-2">
                                {choice.colors.map((color) => (
                                  <li key={color}>
                                    <button
                                      type="button"
                                      onClick={() => choose(finish.code, { colors: choice.colors.filter((other) => other !== color) })}
                                      className="inline-flex cursor-pointer items-center gap-2 rounded-full border border-line px-3 py-1 text-small hover:border-ink"
                                      aria-label={`${color} entfernen`}
                                    >
                                      <ColorDot color={color} size="sm" />
                                      {color} ×
                                    </button>
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <p className="mt-1 text-hint text-ink-tertiary">Ohne Farbe: eine Ausführung in einer Farbe.</p>
                            )}
                            <div className="mt-2 flex gap-2">
                              <label htmlFor={`color-${finish.code}`} className="sr-only">
                                Farbe hinzufügen
                              </label>
                              <Input
                                id={`color-${finish.code}`}
                                value={choice.draft}
                                onChange={(event) => choose(finish.code, { draft: event.target.value })}
                                placeholder="z. B. Rot"
                              />
                              <Button
                                type="button"
                                variant="secondary"
                                onClick={() => {
                                  const color = colorName.safeParse(choice.draft);
                                  if (color.success && color.data !== "" && !choice.colors.includes(color.data)) {
                                    choose(finish.code, { colors: [...choice.colors, color.data], draft: "" });
                                  }
                                }}
                              >
                                Farbe dazu
                              </Button>
                            </div>
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </fieldset>
            <p className="text-small text-ink-secondary">
              {planned.length === 0 ? "Noch keine Ausführung gewählt." : planned.length === 1 ? "Es entsteht 1 Ausführung." : `Es entstehen ${planned.length} Ausführungen.`}
            </p>
            <Problem text={problem} />
            <Actions>
              <Button type="button" variant="secondary" onClick={() => setStep(0)} disabled={pending}>
                Zurück
              </Button>
              <Button type="button" onClick={() => void create()} disabled={pending} aria-busy={pending || undefined}>
                {pending ? "Wird angelegt …" : "Anlegen und weiter"}
              </Button>
            </Actions>
          </>
        ) : null}

        {step === 2 ? (
          <>
            <p className="text-small text-ink-secondary">Wie viele Stücke liegen fertig da, und wo? Ohne Stücke einfach weiter.</p>
            <ul className="space-y-4">
              {made.map((entry) => {
                const count = counts[entry.variantId] ?? { quantity: "0", place: "" };
                const set = (change: Partial<typeof count>) => setCounts((before) => ({ ...before, [entry.variantId]: { ...count, ...change } }));
                const done = booked[entry.variantId];
                return (
                  <li key={entry.variantId} className="rounded-md border border-line p-4">
                    <p className="font-medium">
                      {entry.label}
                      {done !== undefined ? <span className="ml-2 text-small font-normal text-success">{done} eingebucht</span> : null}
                    </p>
                    <div className="mt-3 grid grid-cols-[6rem_minmax(0,1fr)] gap-3">
                      <Field label="Anzahl" htmlFor={`count-${entry.variantId}`}>
                        <Input
                          id={`count-${entry.variantId}`}
                          value={count.quantity}
                          onChange={(event) => set({ quantity: event.target.value })}
                          inputMode="numeric"
                          disabled={done !== undefined}
                        />
                      </Field>
                      <Field label="Platz" htmlFor={`place-${entry.variantId}`}>
                        <Select id={`place-${entry.variantId}`} value={count.place} onChange={(event) => set({ place: event.target.value })} disabled={done !== undefined}>
                          <option value="">Bitte wählen</option>
                          {(places.data ?? []).map((place) => (
                            <option key={place.id} value={place.code}>
                              {place.place}
                            </option>
                          ))}
                        </Select>
                      </Field>
                    </div>
                  </li>
                );
              })}
            </ul>
            <Problem text={problem} />
            <Actions>
              <Button type="button" variant="secondary" onClick={() => setStep(3)} disabled={pending}>
                Überspringen
              </Button>
              <Button type="button" onClick={() => void bookIn()} disabled={pending} aria-busy={pending || undefined}>
                {pending ? "Wird eingebucht …" : "Einbuchen und weiter"}
              </Button>
            </Actions>
          </>
        ) : null}

        {step === 3 ? (
          <>
            <LabelPrinter models={printable} />
            <label className="flex cursor-pointer items-center gap-3 rounded-md border border-line p-4">
              <input type="checkbox" checked={show} onChange={(event) => setShow(event.target.checked)} className="size-5 accent-[var(--selected)]" />
              <span>
                <span className="block font-medium">Gleich im Shop zeigen</span>
                <span className="block text-hint text-ink-tertiary">Braucht ein Foto, einen Preis und eine Kategorie.</span>
              </span>
            </label>
            <Problem text={problem} />
            <Actions>
              <Button type="button" onClick={() => void finish()} disabled={pending} aria-busy={pending || undefined}>
                {pending ? "Einen Moment …" : "Fertig"}
              </Button>
            </Actions>
          </>
        ) : null}
      </div>
    </div>
  );
}

function Field({ label, htmlFor, hint, children }: { label: string; htmlFor: string; hint?: string; children: ReactNode }) {
  return (
    <div>
      <label htmlFor={htmlFor} className="text-small font-medium">
        {label}
      </label>
      <div className="mt-2">{children}</div>
      {hint ? <p className="mt-1 text-hint text-ink-tertiary">{hint}</p> : null}
    </div>
  );
}

function Actions({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap justify-end gap-3 pt-2 [&>*]:max-sm:flex-1">{children}</div>;
}

function Problem({ text }: { text: string | null }) {
  return (
    <p role="alert" className="text-small font-medium text-danger empty:hidden">
      {text}
    </p>
  );
}
