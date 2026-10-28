"use client";

import { useQueryClient } from "@tanstack/react-query";
import type { Route } from "next";
import Link from "next/link";
import {
  useDeferredValue,
  useEffect,
  useId,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
  type ReactNode,
} from "react";

import { LabelPrinter } from "@/components/admin/inventory/label-printer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ColorDot } from "@/components/ui/color-dot";
import { Input } from "@/components/ui/input";
import { OptionGroup, OptionPill } from "@/components/ui/option-pill";
import { QuantityStepper } from "@/components/ui/quantity-stepper";
import { ResponsivePicture } from "@/components/ui/responsive-picture";
import { Select } from "@/components/ui/select";
import { StatusBadge } from "@/components/ui/status-badge";
import { createQuickEntry, useListProducts } from "@/lib/api/generated/admin-catalog/admin-catalog";
import {
  getListLocationsQueryKey,
  getListStockQueryKey,
  labelUnits,
  useListLocations,
} from "@/lib/api/generated/admin-inventory/admin-inventory";
import type { FinishOut, ProductListItemOut, QuickEntryOut, UnitOut } from "@/lib/api/generated/model";
import { isApiProblem } from "@/lib/api/problem";
import { PAINT_SUGGESTIONS, sameColor } from "@/lib/catalog/colors";
import { centsToEuroInput, finishLabel, formatPrice, formatProductNumber } from "@/lib/catalog/format";
import { readyPicture } from "@/lib/catalog/images";
import { PRODUCT_STATUS_LABELS } from "@/lib/catalog/labels";
import { entryPlan, productColors, variantOf, type EntryPlan } from "@/lib/catalog/quick-entry";
import { scaleLabel } from "@/lib/catalog/scales";
import { formatUnitCode } from "@/lib/inventory/codes";
import { errorMessage, fieldErrorMessage } from "@/lib/i18n/problems";
import { IMAGE_PICKER_ACCEPT, uploadImage, type UploadProgress } from "@/lib/media/upload";
import { cn } from "@/lib/utils";
import { colorName, euroPrice } from "@/lib/validation/catalog";

import { categoryOptions } from "./product-details-form";
import { STATUS_TONES } from "./product-list";
import { ADMIN_PRODUCTS_KEY, productQueryKey, useCategories, useProduct, useReferences } from "./use-product";

/** The model on the bench: one from the catalogue (a draft from the stock photos, say) or a new one. */
type Model = { kind: "existing"; product: ProductListItemOut } | { kind: "new"; name: string };

type Photo = {
  previewUrl: string;
  progress: UploadProgress;
  assetId: string | null;
  error: string | null;
};

type Done = { entry: QuickEntryOut; units: UnitOut[]; unitsError: string | null };

/** How many suggestions the colour row shows besides the product's own colours. */
const QUICK_PAINTS = 8;

/**
 * The quick entry for the phone: one model off the shelf in one go. Photo, model,
 * scale, finish, colour and price, optionally the pieces with their labels; the
 * product stays a draft until it is complete and published.
 */
export function QuickEntryDesk() {
  const queryClient = useQueryClient();
  const references = useReferences();
  const priceId = useId();
  const [model, setModel] = useState<Model | null>(null);
  const [categoryId, setCategoryId] = useState("");
  const [scaleCode, setScaleCode] = useState("");
  const [finishCode, setFinishCode] = useState("");
  const [color, setColor] = useState("");
  // Empty until typed: then a variant that exists offers its price.
  const [price, setPrice] = useState<string | null>(null);
  const [quantity, setQuantity] = useState(1);
  const [location, setLocation] = useState("");
  const [photo, setPhoto] = useState<Photo | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [done, setDone] = useState<Done | null>(null);
  const [session, setSession] = useState<Done[]>([]);

  const productId = model?.kind === "existing" ? model.product.id : null;
  const product = useProduct(productId ?? "", { enabled: productId !== null });
  const current = productId !== null && product.data?.id === productId ? product.data : null;

  const scales = references.data?.scales ?? [];
  const finishes = (references.data?.finishes ?? []).filter((finish) => finish.offered);
  const scale = scales.find((s) => s.code === scaleCode) ?? scales[0];
  const finish = finishes.find((f) => f.code === finishCode) ?? finishes[0];
  const paint = finish?.colored ? color.trim() : "";
  const choice = { scaleCode: scale?.code ?? "", finishCode: finish?.code ?? "", color: paint };
  const plan: EntryPlan | null = model === null ? null : entryPlan(current, choice);
  const needsCategory = model?.kind === "new" || (current !== null && current.primary_category_id === null);

  // A variant that exists brings its price along, so a repeat entry is one tap.
  const known = current ? variantOf(current, choice) : undefined;
  const shownPrice = price ?? (known ? centsToEuroInput(known.price_cents) : "");

  const previewUrl = photo?.previewUrl;
  useEffect(
    () => () => {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
      }
    },
    [previewUrl],
  );

  async function takePhoto(file: File) {
    const previewUrl = URL.createObjectURL(file);
    const update = (patch: Partial<Photo>) =>
      setPhoto((now) => (now?.previewUrl === previewUrl ? { ...now, ...patch } : now));
    setPhoto({ previewUrl, progress: { phase: "checking", fraction: 0 }, assetId: null, error: null });
    try {
      const asset = await uploadImage(file, { onProgress: (progress) => update({ progress }) });
      update({ assetId: asset.id });
    } catch (error) {
      update({ error: isApiProblem(error) ? errorMessage(error) : "Das Foto ließ sich nicht hochladen." });
    }
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!model || !scale || !finish) {
      setProblem("Bitte wähle zuerst das Modell.");
      return;
    }
    const parsedPrice = euroPrice.safeParse(shownPrice);
    const parsedColor = colorName.safeParse(paint);
    if (!parsedPrice.success || !parsedColor.success) {
      setProblem((parsedPrice.error ?? parsedColor.error)?.issues[0]?.message ?? null);
      return;
    }
    if (photo && photo.assetId === null && photo.error === null) {
      setProblem("Das Foto lädt noch. Einen Moment, dann noch einmal.");
      return;
    }
    setProblem(null);
    setPending(true);
    try {
      const entry = await createQuickEntry({
        product_id: model.kind === "existing" ? model.product.id : null,
        name: model.kind === "new" ? model.name : null,
        category_id: needsCategory && categoryId !== "" ? categoryId : null,
        scale_code: scale.code,
        finish_code: finish.code,
        color: parsedColor.data,
        price_cents: parsedPrice.data,
        asset_id: photo?.assetId ?? null,
      });
      queryClient.setQueryData(productQueryKey(entry.product.id), entry.product);
      void queryClient.invalidateQueries({ queryKey: ADMIN_PRODUCTS_KEY });
      let units: UnitOut[] = [];
      let unitsError: string | null = null;
      if (quantity > 0) {
        try {
          const batch = await labelUnits({
            variant_id: entry.variant.id,
            quantity,
            location_code: location === "" ? null : location,
          });
          units = batch.items;
          void queryClient.invalidateQueries({ queryKey: getListStockQueryKey() });
          void queryClient.invalidateQueries({ queryKey: getListLocationsQueryKey() });
        } catch (error) {
          unitsError = errorMessage(error);
        }
      }
      const result = { entry, units, unitsError };
      setDone(result);
      setSession((before) => [result, ...before]);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (error) {
      const field = isApiProblem(error) ? error.fieldErrors[0] : undefined;
      setProblem(field ? fieldErrorMessage(field.field, field.code) : errorMessage(error));
    } finally {
      setPending(false);
    }
  }

  /** The next model from the crate: scale, finish and category stay, like the shelf. */
  function next({ sameModel }: { sameModel: boolean }) {
    if (done && sameModel) {
      const entry = done.entry;
      setModel({ kind: "existing", product: listItemOf(entry) });
    } else {
      setModel(null);
      setPrice(null);
    }
    setColor("");
    setPhoto(null);
    setProblem(null);
    setDone(null);
  }

  if (references.isError) {
    return <p className="text-small text-danger">{errorMessage(references.error)}</p>;
  }

  return (
    <div className="mx-auto max-w-2xl">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="label-caps text-ink-tertiary">Katalog</p>
          <h1 className="mt-3 text-heading sm:text-title">Schnellerfassung</h1>
          <p className="mt-2 text-small text-ink-secondary">
            Ein Modell aus der Kiste: Foto, Ausführung, Preis – fertig. Neues bleibt Entwurf, bis es vollständig ist.
          </p>
        </div>
        {session.length > 0 ? <SessionTally entries={session} /> : null}
      </header>

      {done ? (
        <DoneCard done={done} finishes={references.data?.finishes ?? []} onNext={next} />
      ) : (
        <form noValidate onSubmit={onSubmit} aria-label="Modell erfassen" className="mt-8 space-y-4 pb-28">
          <Step number="01" title="Foto" hint="Optional, aber jedes Foto spart später Arbeit.">
            <PhotoField photo={photo} onPick={(file) => void takePhoto(file)} onClear={() => setPhoto(null)} />
          </Step>

          <Step number="02" title="Modell">
            <ModelField model={model} onChange={setModel} />
            {needsCategory ? <CategoryField value={categoryId} onChange={setCategoryId} /> : null}
          </Step>

          <Step number="03" title="Ausführung">
            <div className="space-y-5">
              {scales.length > 0 ? (
                <OptionGroup label="Maßstab" value={scale?.code ?? ""} onValueChange={setScaleCode}>
                  {scales.map((option) => (
                    <OptionPill key={option.code} value={option.code} aria-label={scaleLabel(option)}>
                      {option.name}
                    </OptionPill>
                  ))}
                </OptionGroup>
              ) : null}
              {finishes.length > 0 ? (
                <OptionGroup label="Ausführung" value={finish?.code ?? ""} onValueChange={setFinishCode}>
                  {finishes.map((option) => (
                    <OptionPill key={option.code} value={option.code}>
                      {option.name}
                    </OptionPill>
                  ))}
                </OptionGroup>
              ) : null}
              {finish?.colored ? (
                <ColorField value={color} onChange={setColor} own={productColors(current)} />
              ) : (
                <p className="text-hint text-ink-tertiary">Ein Bausatz kommt ohne Farbe.</p>
              )}
            </div>
          </Step>

          <Step number="04" title="Preis und Bestand">
            <div className="grid gap-5 sm:grid-cols-2">
              <div>
                <label htmlFor={priceId} className="block text-hint text-ink-tertiary">
                  Preis
                </label>
                <span className="relative mt-1 block">
                  <Input
                    id={priceId}
                    inputMode="decimal"
                    value={shownPrice}
                    onChange={(event) => setPrice(event.target.value)}
                    placeholder="49,90"
                    className="pr-10 text-[1.25rem] tabular-nums"
                  />
                  <span
                    aria-hidden="true"
                    className="pointer-events-none absolute inset-y-0 right-4 flex items-center text-ink-tertiary"
                  >
                    €
                  </span>
                </span>
              </div>
              <div>
                <span aria-hidden="true" className="block text-hint text-ink-tertiary">
                  Stück mit Etikett
                </span>
                <QuantityStepper
                  value={quantity}
                  onChange={setQuantity}
                  min={0}
                  max={200}
                  label="Stück mit Etikett"
                  className="mt-1"
                />
              </div>
              {quantity > 0 ? <LocationField value={location} onChange={setLocation} /> : null}
            </div>
          </Step>

          <div className="sticky bottom-0 z-10 -mx-5 border-t border-line bg-surface/95 px-5 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur sm:mx-0 sm:rounded-md sm:border">
            <PlanLine
              plan={plan}
              model={model}
              choice={finishLabel(finish?.name ?? "", paint)}
              scale={scale?.name ?? ""}
            />
            <p role="alert" className="text-small font-medium text-danger empty:hidden">
              {problem}
            </p>
            <Button
              type="submit"
              disabled={pending || model === null}
              aria-busy={pending || undefined}
              className="mt-2 w-full"
            >
              {pending
                ? "Wird erfasst …"
                : quantity > 0
                  ? `Erfassen · ${quantity} Etikett${quantity === 1 ? "" : "en"}`
                  : "Erfassen"}
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}

function listItemOf(entry: QuickEntryOut): ProductListItemOut {
  const { product } = entry;
  return {
    id: product.id,
    name: product.name,
    number: product.number,
    slug: product.slug,
    status: product.status,
    main_image: product.media[0]?.image ?? null,
    price_from_cents: null,
    published_at: product.published_at,
    scale_codes: product.scales.map((s) => s.scale_code),
    updated_at: product.updated_at,
    variant_count: product.scales.reduce((sum, s) => sum + s.variants.length, 0),
  };
}

function Step({
  number,
  title,
  hint,
  children,
}: {
  number: string;
  title: string;
  hint?: string;
  children: ReactNode;
}) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className="rounded-md border border-line bg-surface p-4 sm:p-5">
      <header className="mb-4 flex items-baseline gap-3">
        <span aria-hidden="true" className="font-mono text-hint text-ink-tertiary">
          {number}
        </span>
        <h2 id={headingId} className="text-body font-medium tracking-normal">
          {title}
        </h2>
        {hint ? <p className="ml-auto text-hint text-ink-tertiary max-sm:hidden">{hint}</p> : null}
      </header>
      {children}
    </section>
  );
}

const PHASES = { checking: "Wird geprüft", uploading: "Lädt hoch", completing: "Wird übergeben" } as const;

function PhotoField({
  photo,
  onPick,
  onClear,
}: {
  photo: Photo | null;
  onPick: (file: File) => void;
  onClear: () => void;
}) {
  const camera = useRef<HTMLInputElement>(null);
  const gallery = useRef<HTMLInputElement>(null);
  function picked(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) {
      onPick(file);
    }
  }
  const status = photo?.error
    ? photo.error
    : photo?.assetId
      ? "Hochgeladen"
      : photo
        ? `${PHASES[photo.progress.phase]}${photo.progress.phase === "uploading" ? ` ${Math.round(photo.progress.fraction * 100)} %` : ""}`
        : null;

  return (
    <div>
      <input
        ref={camera}
        type="file"
        accept={IMAGE_PICKER_ACCEPT}
        capture="environment"
        onChange={picked}
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
      />
      <input
        ref={gallery}
        type="file"
        accept={IMAGE_PICKER_ACCEPT}
        onChange={picked}
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
      />
      {photo ? (
        <figure className="relative m-0 overflow-hidden rounded-md bg-stage">
          {/* eslint-disable-next-line @next/next/no-img-element -- a local preview of the file, no rendition yet */}
          <img src={photo.previewUrl} alt="Vorschau des Fotos" className="mx-auto aspect-[4/3] w-full object-contain" />
          <figcaption className="flex items-center justify-between gap-3 border-t border-line bg-surface px-3 py-2">
            <span
              className={cn(
                "text-hint",
                photo.error ? "text-danger" : photo.assetId ? "text-success" : "text-ink-secondary",
              )}
              role="status"
            >
              {status}
            </span>
            <span className="flex gap-1">
              <Button type="button" variant="ghost" size="sm" onClick={() => camera.current?.click()}>
                Neu aufnehmen
              </Button>
              <Button type="button" variant="ghost" size="sm" onClick={onClear}>
                Ohne Foto
              </Button>
            </span>
          </figcaption>
          {photo.assetId === null && photo.error === null ? (
            <span
              aria-hidden="true"
              className="absolute inset-x-0 top-0 h-1 origin-left bg-accent transition-transform duration-200"
              style={{ transform: `scaleX(${photo.progress.phase === "uploading" ? photo.progress.fraction : 0.08})` }}
            />
          ) : null}
        </figure>
      ) : (
        <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-2">
          <button
            type="button"
            onClick={() => camera.current?.click()}
            className="group flex aspect-[4/3] max-h-64 w-full cursor-pointer flex-col items-center justify-center gap-3 rounded-md border border-dashed border-line-strong bg-stage text-ink-secondary transition-colors hover:border-ink hover:text-ink sm:aspect-[16/7]"
          >
            <CameraGlyph />
            <span className="text-small font-medium">Foto aufnehmen</span>
          </button>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            className="self-end"
            onClick={() => gallery.current?.click()}
          >
            Aus Galerie
          </Button>
        </div>
      )}
    </div>
  );
}

/** A camera in the drawing style of the shop: fine Prussian-blue lines. */
function CameraGlyph() {
  return (
    <svg viewBox="0 0 64 48" className="h-12 w-16" aria-hidden="true">
      <g className="fill-none stroke-drawing-line" strokeWidth="1" vectorEffect="non-scaling-stroke">
        <path d="M6 14h12l4-6h20l4 6h12v28H6z" vectorEffect="non-scaling-stroke" />
        <circle cx="32" cy="27" r="10" vectorEffect="non-scaling-stroke" />
        <circle cx="32" cy="27" r="6" vectorEffect="non-scaling-stroke" />
        <path d="M50 19h4" vectorEffect="non-scaling-stroke" />
      </g>
      <g className="fill-none stroke-drawing-helper [stroke-dasharray:2_2]" strokeWidth="1">
        <path d="M32 12v30M16 27h32" vectorEffect="non-scaling-stroke" />
      </g>
    </svg>
  );
}

function ModelField({ model, onChange }: { model: Model | null; onChange: (model: Model | null) => void }) {
  const [search, setSearch] = useState("");
  const query = useDeferredValue(search.trim());
  const products = useListProducts(
    { q: query || null, limit: 6 },
    { query: { enabled: model === null && query !== "" } },
  );

  if (model?.kind === "existing") {
    const picture = readyPicture(model.product.main_image);
    return (
      <div className="flex items-center gap-4 rounded-sm border border-line bg-canvas p-3">
        <span className="relative size-14 shrink-0 rounded-sm bg-stage p-1">
          {picture ? <ResponsivePicture image={picture} alt="" sizes="56px" variant="thumb" /> : null}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-small font-medium">{model.product.name}</span>
          <span className="mt-1 flex flex-wrap items-center gap-2">
            <span className="font-mono text-hint text-ink-tertiary">{formatProductNumber(model.product.number)}</span>
            <StatusBadge tone={STATUS_TONES[model.product.status]}>
              {PRODUCT_STATUS_LABELS[model.product.status]}
            </StatusBadge>
          </span>
        </span>
        <Button type="button" size="sm" variant="ghost" onClick={() => onChange(null)}>
          Ändern
        </Button>
      </div>
    );
  }
  if (model?.kind === "new") {
    return (
      <div className="flex items-center gap-4 rounded-sm border border-line bg-canvas p-3">
        <span className="min-w-0 flex-1">
          <span className="block truncate text-small font-medium">{model.name}</span>
          <Badge tone="accent" className="mt-1">
            Neues Produkt
          </Badge>
        </span>
        <Button type="button" size="sm" variant="ghost" onClick={() => onChange(null)}>
          Ändern
        </Button>
      </div>
    );
  }

  const exact = products.data?.items.some(
    (item) => item.name.toLocaleLowerCase("de-DE") === query.toLocaleLowerCase("de-DE"),
  );
  return (
    <div className="space-y-2">
      <label className="block">
        <span className="block text-hint text-ink-tertiary">Name oder Nummer</span>
        <Input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="z. B. ADK 70 oder Tatra"
          autoComplete="off"
          enterKeyHint="search"
          className="mt-1"
        />
      </label>
      {query !== "" ? (
        <ul className="divide-y divide-line overflow-hidden rounded-sm border border-line">
          {products.isPending ? <li className="px-4 py-3 text-small text-ink-secondary">Wird gesucht …</li> : null}
          {products.isError ? (
            <li className="px-4 py-3 text-small text-danger">{errorMessage(products.error)}</li>
          ) : null}
          {products.data?.items.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                onClick={() => onChange({ kind: "existing", product: item })}
                className="flex w-full cursor-pointer items-center justify-between gap-3 px-4 py-3 text-left hover:bg-sunken"
              >
                <span className="min-w-0">
                  <span className="block truncate text-small font-medium">{item.name}</span>
                  <span className="block font-mono text-hint text-ink-tertiary">
                    {formatProductNumber(item.number)}
                    {item.scale_codes.length > 0 ? ` · ${item.scale_codes.join(" · ")}` : ""}
                  </span>
                </span>
                <StatusBadge tone={STATUS_TONES[item.status]}>{PRODUCT_STATUS_LABELS[item.status]}</StatusBadge>
              </button>
            </li>
          ))}
          {!exact && products.isSuccess ? (
            <li>
              <button
                type="button"
                onClick={() => onChange({ kind: "new", name: search.trim().replace(/\s+/g, " ") })}
                className="flex w-full cursor-pointer items-center gap-3 px-4 py-3 text-left text-accent hover:bg-accent-subtle"
              >
                <span aria-hidden="true" className="text-heading leading-none font-extralight">
                  +
                </span>
                <span className="text-small font-medium">„{search.trim()}“ neu anlegen</span>
              </button>
            </li>
          ) : null}
        </ul>
      ) : null}
    </div>
  );
}

function CategoryField({ value, onChange }: { value: string; onChange: (id: string) => void }) {
  const categories = useCategories();
  return (
    <label className="mt-4 block">
      <span className="block text-hint text-ink-tertiary">Kategorie</span>
      <Select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={categories.isPending}
        className="mt-1"
      >
        <option value="">Später festlegen</option>
        {categoryOptions(categories.data ?? []).map(({ category, depth }) => (
          <option key={category.id} value={category.id}>
            {" ".repeat(depth)}
            {category.name}
          </option>
        ))}
      </Select>
    </label>
  );
}

function ColorField({
  value,
  onChange,
  own,
}: {
  value: string;
  onChange: (color: string) => void;
  own: readonly string[];
}) {
  const listId = useId();
  const quick = [...own, ...PAINT_SUGGESTIONS.filter((name) => !own.some((c) => sameColor(c, name)))].slice(
    0,
    Math.max(QUICK_PAINTS, own.length),
  );
  return (
    <div>
      <label className="block">
        <span className="block text-hint text-ink-tertiary">Farbe</span>
        <span className="mt-1 flex items-center gap-3">
          <Input
            value={value}
            onChange={(event) => onChange(event.target.value)}
            placeholder="einfarbig lassen oder z. B. Gelb"
            maxLength={40}
            list={listId}
          />
          {value.trim() !== "" ? <ColorDot color={value} /> : null}
        </span>
      </label>
      <datalist id={listId}>
        {PAINT_SUGGESTIONS.map((name) => (
          <option key={name} value={name} />
        ))}
      </datalist>
      <ul className="mt-3 flex flex-wrap gap-2" aria-label="Häufige Farben">
        {quick.map((name) => {
          const chosen = sameColor(name, value.trim());
          return (
            <li key={name}>
              <button
                type="button"
                aria-pressed={chosen}
                onClick={() => onChange(chosen ? "" : name)}
                className={cn(
                  "inline-flex h-9 cursor-pointer items-center gap-2 rounded-full border pr-3.5 pl-2 text-sm transition-colors",
                  chosen ? "border-selected bg-selected text-on-selected" : "border-line-strong hover:border-ink",
                  own.includes(name) && !chosen && "border-accent",
                )}
              >
                <ColorDot color={name} size="sm" className={chosen ? "ring-2 ring-on-selected" : undefined} />
                {name}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function LocationField({ value, onChange }: { value: string; onChange: (code: string) => void }) {
  const locations = useListLocations({ query: { select: (tree) => tree.items.filter((item) => item.holds_goods) } });
  return (
    <label className="block sm:col-span-2">
      <span className="block text-hint text-ink-tertiary">Platz</span>
      <Select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={locations.isPending}
        className="mt-1"
      >
        <option value="">Später beim Einlagern scannen</option>
        {(locations.data ?? []).map((item) => (
          <option key={item.id} value={item.code}>
            {item.code}
            {item.name ? ` · ${item.name}` : ""}
          </option>
        ))}
      </Select>
    </label>
  );
}

/** What tapping the button will do, in one line. */
function PlanLine({
  plan,
  model,
  choice,
  scale,
}: {
  plan: EntryPlan | null;
  model: Model | null;
  choice: string;
  scale: string;
}) {
  if (plan === null || model === null) {
    return <p className="text-hint text-ink-tertiary">Zuerst das Modell suchen oder neu anlegen.</p>;
  }
  const what = `${scale} · ${choice}`;
  const text =
    plan.kind === "new-product"
      ? `Neues Produkt mit ${what}`
      : plan.kind === "new-variant"
        ? `Neue Variante ${what}${plan.newScale ? `, erster Artikel in ${scale}` : ""}`
        : `${what} gibt es schon (${plan.variant.sku}) · Preis bisher ${formatPrice(plan.variant.price_cents)}`;
  return (
    <p className="flex items-center gap-2 text-hint text-ink-secondary">
      <span
        aria-hidden="true"
        className={cn("size-2 shrink-0 rounded-full", plan.kind === "existing" ? "bg-accent" : "bg-success")}
      />
      <span className="truncate">{text}</span>
    </p>
  );
}

type DoneCardProps = {
  done: Done;
  finishes: readonly FinishOut[];
  onNext: (options: { sameModel: boolean }) => void;
};

function DoneCard({ done, finishes, onNext }: DoneCardProps) {
  const { entry, units, unitsError } = done;
  const scale = entry.product.scales.find((s) => s.variants.some((v) => v.id === entry.variant.id));
  const finish = finishes.find((f) => f.code === entry.variant.finish_code);
  return (
    <section aria-label="Erfasst" className="mt-8 overflow-hidden rounded-md border border-line bg-surface">
      <div className="flex items-start gap-4 border-b border-line bg-stage p-5">
        <span
          aria-hidden="true"
          className="grid size-10 shrink-0 place-items-center rounded-full bg-success text-on-selected"
        >
          <svg viewBox="0 0 16 16" className="size-5">
            <path
              d="M3.5 8.5l3 3 6-7"
              className="fill-none stroke-current"
              strokeWidth="1.75"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
        <div className="min-w-0">
          <h2 className="text-body font-medium tracking-normal">{entry.product.name}</h2>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-small text-ink-secondary">
            {entry.variant.color !== "" ? <ColorDot color={entry.variant.color} size="sm" /> : null}
            {scale?.scale_code} · {finishLabel(finish?.name ?? entry.variant.finish_code, entry.variant.color)} ·{" "}
            {formatPrice(entry.variant.price_cents)}
          </p>
          <p className="mt-1 font-mono text-hint text-ink-tertiary">{entry.variant.sku}</p>
          <p className="mt-3 flex flex-wrap gap-2">
            {entry.new_product ? <Badge tone="accent">Neues Produkt</Badge> : null}
            {entry.new_variant ? <Badge tone="success">Neue Variante</Badge> : <Badge>Preis gesetzt</Badge>}
            <StatusBadge tone={STATUS_TONES[entry.product.status]}>
              {PRODUCT_STATUS_LABELS[entry.product.status]}
            </StatusBadge>
          </p>
        </div>
      </div>
      <div className="space-y-5 p-5">
        {unitsError ? (
          <p role="alert" className="text-small text-danger">
            Das Modell ist erfasst, die Stücke aber nicht: {unitsError}
          </p>
        ) : null}
        {units.length > 0 ? (
          <div>
            <p className="label-caps text-ink-tertiary">{units.length === 1 ? "1 Stück" : `${units.length} Stück`}</p>
            <ul className="mt-2 flex flex-wrap gap-1.5">
              {units.slice(0, 12).map((unit) => (
                <li key={unit.id} className="rounded-xs bg-sunken px-2 py-1 font-mono text-hint">
                  {formatUnitCode(unit.code)}
                </li>
              ))}
              {units.length > 12 ? (
                <li className="px-2 py-1 text-hint text-ink-tertiary">+ {units.length - 12}</li>
              ) : null}
            </ul>
            <LabelPrinter unitCodes={units.map((unit) => unit.code)} className="mt-5" />
          </div>
        ) : null}
        {entry.product.publish_blockers.length > 0 ? (
          <p className="text-hint text-ink-tertiary">Fürs Veröffentlichen fehlt noch etwas; im Katalog steht, was.</p>
        ) : null}
        <div className="grid gap-2 sm:grid-cols-2">
          <Button type="button" onClick={() => onNext({ sameModel: false })}>
            Nächstes Modell
          </Button>
          <Button type="button" variant="secondary" onClick={() => onNext({ sameModel: true })}>
            Gleiches Modell, andere Farbe
          </Button>
          <Button asChild variant="ghost" className="sm:col-span-2">
            <Link href={`/admin/katalog/${entry.product.id}` as Route}>Im Katalog öffnen</Link>
          </Button>
        </div>
      </div>
    </section>
  );
}

function SessionTally({ entries }: { entries: readonly Done[] }) {
  const pieces = entries.reduce((sum, entry) => sum + entry.units.length, 0);
  return (
    <p className="rounded-full border border-line px-3 py-1 text-hint text-ink-secondary tabular-nums">
      {entries.length} erfasst{pieces > 0 ? ` · ${pieces} Stück` : ""}
    </p>
  );
}
