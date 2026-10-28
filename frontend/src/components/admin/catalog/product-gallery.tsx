"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type ChangeEvent, type DragEvent } from "react";

import { Panel } from "@/components/admin/panel";
import { Button } from "@/components/ui/button";
import { ColorDot } from "@/components/ui/color-dot";
import { Input } from "@/components/ui/input";
import { ResponsivePicture } from "@/components/ui/responsive-picture";
import { Select } from "@/components/ui/select";
import { StatusBadge, type StatusTone } from "@/components/ui/status-badge";
import { arrangeProductGallery, attachProductImage } from "@/lib/api/generated/admin-catalog/admin-catalog";
import type {
  AdminImageOut,
  AssetStatus,
  GalleryEntryIn,
  GalleryItemOut,
  MediaRole,
  ProductOut,
  ReferencesOut,
} from "@/lib/api/generated/model";
import { isApiProblem } from "@/lib/api/problem";
import { sameColor } from "@/lib/catalog/colors";
import { readyPicture } from "@/lib/catalog/images";
import { ASSET_STATUS_LABELS, failureLabel, MEDIA_ROLE_LABELS } from "@/lib/catalog/labels";
import { ifMatch } from "@/lib/catalog/versions";
import { errorMessage } from "@/lib/i18n/problems";
import {
  IMAGE_PICKER_ACCEPT,
  StorageUploadError,
  UnsuitableFileError,
  uploadImage,
  type UploadProgress,
} from "@/lib/media/upload";
import { cn } from "@/lib/utils";

import { productQueryKey, useProductCommand } from "./use-product";

const STATUS_TONES = {
  pending_upload: "accent",
  uploaded: "accent",
  ready: "success",
  failed: "danger",
} as const satisfies Record<AssetStatus, StatusTone>;

type Upload = { id: string; name: string; progress: UploadProgress; error?: string };

function entryOf(item: GalleryItemOut): GalleryEntryIn {
  return {
    asset_id: item.asset_id,
    role: item.role,
    alt_text: item.alt_text,
    scale_code: item.scale_code,
    finish_code: item.finish_code,
    color: item.color,
  };
}

/** Every colour of the product, once, in the order of the alphabet. */
function productColors(product: ProductOut): string[] {
  const all = product.scales.flatMap((scale) => scale.variants.map((variant) => variant.color));
  return [...new Set(all.filter((color) => color !== ""))].sort((a, b) => a.localeCompare(b, "de"));
}

/**
 * Keeps local edits of the gallery while the server state moves on (an upload
 * finished, a photo got processed): entries that are gone are dropped, new ones
 * are appended, the rest keeps its local order and texts.
 */
export function mergeDraft(draft: readonly GalleryEntryIn[], server: readonly GalleryItemOut[]): GalleryEntryIn[] {
  const onServer = new Set(server.map((item) => item.asset_id));
  const kept = draft.filter((entry) => onServer.has(entry.asset_id));
  const known = new Set(kept.map((entry) => entry.asset_id));
  return [...kept, ...server.filter((item) => !known.has(item.asset_id)).map(entryOf)];
}

function uploadErrorMessage(error: unknown): string {
  if (error instanceof UnsuitableFileError) {
    return error.reason === "type"
      ? "Kein Bildformat, das wir lesen können (JPEG, PNG, WebP, AVIF, HEIC)."
      : "Die Datei ist größer als 50 MB.";
  }
  if (error instanceof StorageUploadError) {
    return "Der Upload in den Speicher ist fehlgeschlagen. Bitte versuche es noch einmal.";
  }
  return isApiProblem(error) ? errorMessage(error) : "Der Upload ist fehlgeschlagen.";
}

type ProductGalleryProps = { product: ProductOut; references: ReferencesOut };

/**
 * The gallery: upload photos (several at once, straight into the object storage),
 * watch them being processed live, then order them and give each an alt text. The
 * first photo is the main image of the shop.
 */
export function ProductGallery({ product, references }: ProductGalleryProps) {
  const queryClient = useQueryClient();
  const save = useProductCommand(product.id);
  // Local edits, or null while the gallery shows the server state as it is.
  const [edits, setEdits] = useState<GalleryEntryIn[] | null>(null);
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [dragging, setDragging] = useState(false);
  const picker = useRef<HTMLInputElement>(null);
  const images = new Map(product.media.map((item) => [item.asset_id, item.image]));
  const dirty = edits !== null;
  const draft = edits === null ? product.media.map(entryOf) : mergeDraft(edits, product.media);
  const colors = productColors(product);

  function change(next: GalleryEntryIn[]) {
    setEdits(next);
  }

  function move(index: number, to: number) {
    const next = [...draft];
    const [entry] = next.splice(index, 1);
    if (entry) {
      next.splice(to, 0, entry);
      change(next);
    }
  }

  function edit(index: number, patch: Partial<GalleryEntryIn>) {
    change(draft.map((entry, position) => (position === index ? { ...entry, ...patch } : entry)));
  }

  async function upload(file: File) {
    const id = `${file.name}-${file.size}-${crypto.randomUUID()}`;
    const update = (patch: Partial<Upload>) =>
      setUploads((current) => current.map((item) => (item.id === id ? { ...item, ...patch } : item)));
    setUploads((current) => [...current, { id, name: file.name, progress: { phase: "checking", fraction: 0 } }]);
    try {
      const asset = await uploadImage(file, { onProgress: (progress) => update({ progress }) });
      const updated = await attachProductImage(product.id, { asset_id: asset.id, alt_text: "" });
      queryClient.setQueryData(productQueryKey(product.id), updated);
      setUploads((current) => current.filter((item) => item.id !== id));
    } catch (error) {
      update({ error: uploadErrorMessage(error) });
    }
  }

  function addFiles(files: FileList | null) {
    for (const file of Array.from(files ?? [])) {
      void upload(file);
    }
  }

  function onPick(event: ChangeEvent<HTMLInputElement>) {
    addFiles(event.target.files);
    event.target.value = "";
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    addFiles(event.dataTransfer.files);
  }

  function onSave() {
    save.mutate(() => arrangeProductGallery(product.id, { entries: draft }, ifMatch(product.version)), {
      onSuccess: () => setEdits(null),
    });
  }

  return (
    <Panel
      title="Galerie"
      code="PRD 04"
      actions={
        <span className="text-hint text-ink-tertiary">
          {draft.length === 1 ? "1 Foto" : `${draft.length} Fotos`} · das erste ist das Hauptbild
        </span>
      }
    >
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          "flex flex-col items-center justify-center gap-3 rounded-md border border-dashed px-6 py-8 text-center transition-colors",
          dragging ? "border-accent bg-accent-subtle" : "border-line-strong bg-stage",
        )}
      >
        <p className="text-small text-ink-secondary">
          Fotos hierher ziehen oder auswählen. JPEG, PNG, WebP, AVIF oder HEIC bis 50 MB.
        </p>
        <Button type="button" variant="secondary" size="sm" onClick={() => picker.current?.click()}>
          Fotos auswählen
        </Button>
        <input
          ref={picker}
          type="file"
          multiple
          accept={IMAGE_PICKER_ACCEPT}
          onChange={onPick}
          className="sr-only"
          tabIndex={-1}
          aria-hidden="true"
        />
      </div>

      {uploads.length > 0 ? (
        <ul aria-label="Uploads" className="mt-5 space-y-2">
          {uploads.map((item) => (
            <UploadRow key={item.id} upload={item} onDismiss={() => setUploads((c) => c.filter((u) => u.id !== item.id))} />
          ))}
        </ul>
      ) : null}

      {draft.length > 0 ? (
        <ol className="mt-6 grid gap-4 sm:grid-cols-2">
          {draft.map((entry, index) => (
            <GalleryTile
              key={entry.asset_id}
              entry={entry}
              image={images.get(entry.asset_id) ?? null}
              index={index}
              count={draft.length}
              references={references}
              scaleCodes={product.scales.map((s) => s.scale_code)}
              colors={colors}
              onMove={move}
              onEdit={edit}
              onRemove={() => change(draft.filter((_, position) => position !== index))}
            />
          ))}
        </ol>
      ) : null}

      {dirty ? (
        <div className="mt-6 flex flex-wrap items-center gap-4 border-t border-line pt-5">
          <Button type="button" disabled={save.isPending} aria-busy={save.isPending || undefined} onClick={onSave}>
            {save.isPending ? "Speichert …" : "Galerie speichern"}
          </Button>
          <Button
            type="button"
            variant="ghost"
            onClick={() => setEdits(null)}
          >
            Verwerfen
          </Button>
          <p role="alert" className="text-small text-danger">
            {save.isError ? errorMessage(save.error) : null}
          </p>
        </div>
      ) : null}
    </Panel>
  );
}

const PHASE_LABELS = {
  checking: "Prüfsumme und Ticket",
  uploading: "Wird hochgeladen",
  completing: "Wird abgeschlossen",
} as const;

function UploadRow({ upload, onDismiss }: { upload: Upload; onDismiss: () => void }) {
  const percent = Math.round(upload.progress.fraction * 100);
  return (
    <li className="rounded-sm border border-line px-4 py-3">
      <div className="flex items-center justify-between gap-4">
        <p className="min-w-0 truncate text-small font-medium">{upload.name}</p>
        {upload.error ? (
          <Button type="button" variant="ghost" size="sm" onClick={onDismiss}>
            Ausblenden
          </Button>
        ) : (
          <StatusBadge tone="accent" busy>
            {upload.progress.phase === "uploading" ? `${PHASE_LABELS.uploading} · ${percent} %` : PHASE_LABELS[upload.progress.phase]}
          </StatusBadge>
        )}
      </div>
      {upload.error ? (
        <p role="alert" className="mt-1 text-hint text-danger">
          {upload.error}
        </p>
      ) : (
        <div
          role="progressbar"
          aria-label={`Upload ${upload.name}`}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
          className="mt-2 h-1 overflow-hidden rounded-full bg-sunken"
        >
          <div className="h-full bg-accent transition-[width] duration-200" style={{ width: `${percent}%` }} />
        </div>
      )}
    </li>
  );
}

type GalleryTileProps = {
  entry: GalleryEntryIn;
  image: AdminImageOut | null;
  index: number;
  count: number;
  references: ReferencesOut;
  scaleCodes: readonly string[];
  /** The colours the product comes in, to say which one a photo shows. */
  colors: readonly string[];
  onMove: (from: number, to: number) => void;
  onEdit: (index: number, patch: Partial<GalleryEntryIn>) => void;
  onRemove: () => void;
};

function GalleryTile({
  entry,
  image,
  index,
  count,
  references,
  scaleCodes,
  colors,
  onMove,
  onEdit,
  onRemove,
}: GalleryTileProps) {
  const picture = readyPicture(image);
  // A tag from before keeps its option even when no variant has the colour any more.
  const tileColors = entry.color && !colors.some((c) => sameColor(c, entry.color ?? "")) ? [...colors, entry.color] : colors;
  const coloredFinish = references.finishes.find((finish) => finish.colored)?.code ?? null;
  const status = image?.status ?? "failed";
  const label = `Foto ${index + 1}${index === 0 ? " (Hauptbild)" : ""}`;
  return (
    <li aria-label={label} className={cn("rounded-md border bg-surface", index === 0 ? "border-selected" : "border-line")}>
      <div className="relative aspect-square rounded-t-md bg-stage">
        {picture ? (
          <div className="absolute inset-4">
            <ResponsivePicture image={picture} alt={entry.alt_text ?? ""} sizes="(min-width: 640px) 30vw, 90vw" />
          </div>
        ) : (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 px-4 text-center">
            <StatusBadge tone={STATUS_TONES[status]} busy={status === "uploaded" || status === "pending_upload"}>
              {ASSET_STATUS_LABELS[status]}
            </StatusBadge>
            {status === "failed" ? <p className="text-hint text-ink-secondary">{failureLabel(image?.failure_code ?? null)}</p> : null}
            {image ? <p className="max-w-full truncate font-mono text-[0.6875rem] text-ink-tertiary">{image.filename}</p> : null}
          </div>
        )}
        {index === 0 ? (
          <span className="absolute top-3 left-3 rounded-full bg-selected px-2.5 py-0.5 text-hint font-medium text-on-selected">
            Hauptbild
          </span>
        ) : null}
      </div>
      <div className="space-y-3 p-3">
        <label className="block">
          <span className="block text-hint text-ink-tertiary">Alternativtext</span>
          <Input
            value={entry.alt_text ?? ""}
            maxLength={250}
            placeholder="Was zeigt das Foto?"
            onChange={(event) => onEdit(index, { alt_text: event.target.value })}
            className="mt-1"
          />
        </label>
        <div className="grid grid-cols-2 gap-2">
          <label className="col-span-2">
            <span className="block text-hint text-ink-tertiary">Art</span>
            <Select
              value={entry.role ?? "gallery"}
              onChange={(event) => onEdit(index, { role: event.target.value as MediaRole })}
              className="mt-1"
            >
              {Object.entries(MEDIA_ROLE_LABELS).map(([value, text]) => (
                <option key={value} value={value}>
                  {text}
                </option>
              ))}
            </Select>
          </label>
          <label>
            <span className="block text-hint text-ink-tertiary">Spur</span>
            <Select
              value={entry.scale_code ?? ""}
              onChange={(event) => onEdit(index, { scale_code: event.target.value || null })}
              className="mt-1"
            >
              <option value="">alle</option>
              {scaleCodes.map((code) => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
            </Select>
          </label>
          <label>
            <span className="block text-hint text-ink-tertiary">Ausführung</span>
            <Select
              value={entry.finish_code ?? ""}
              onChange={(event) => onEdit(index, { finish_code: event.target.value || null })}
              className="mt-1"
            >
              <option value="">alle</option>
              {references.finishes
                .filter((finish) => finish.offered || finish.code === entry.finish_code)
                .map((finish) => (
                  <option key={finish.code} value={finish.code}>
                    {finish.name}
                  </option>
                ))}
            </Select>
          </label>
          {tileColors.length > 0 ? (
            <label className="col-span-2">
              <span className="block text-hint text-ink-tertiary">Farbe</span>
              <span className="mt-1 flex items-center gap-2">
                <Select
                  value={entry.color ?? ""}
                  onChange={(event) =>
                    onEdit(index, {
                      color: event.target.value || null,
                      // A colour is a finished model's: tagging one says so too.
                      ...(event.target.value && entry.finish_code === null ? { finish_code: coloredFinish } : {}),
                    })
                  }
                >
                  <option value="">alle</option>
                  {tileColors.map((color) => (
                    <option key={color} value={color}>
                      {color}
                    </option>
                  ))}
                </Select>
                {entry.color ? <ColorDot color={entry.color} /> : null}
              </span>
            </label>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-1">
          <Button type="button" variant="ghost" size="sm" disabled={index === 0} onClick={() => onMove(index, 0)}>
            Als Hauptbild
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={index === 0}
            aria-label={`${label} nach vorn`}
            onClick={() => onMove(index, index - 1)}
          >
            ←
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={index === count - 1}
            aria-label={`${label} nach hinten`}
            onClick={() => onMove(index, index + 1)}
          >
            →
          </Button>
          <Button type="button" variant="ghost" size="sm" className="ml-auto" onClick={onRemove}>
            Entfernen
          </Button>
        </div>
      </div>
    </li>
  );
}
