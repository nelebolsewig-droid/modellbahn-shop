"use client";

import { useId, useState } from "react";

import { IMAGE_PICKER_ACCEPT } from "@/lib/media/upload";
import { cn } from "@/lib/utils";

/**
 * Where the photos of a new model go: a large field to drop them on or tap, and on the
 * phone a second button that opens the camera straight away.
 */
export function PhotoDrop({ onFiles, count }: { onFiles: (files: FileList | null) => void; count: number }) {
  const id = useId();
  const [over, setOver] = useState(false);
  return (
    <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
      <label
        htmlFor={`${id}-pick`}
        onDragOver={(event) => {
          event.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(event) => {
          event.preventDefault();
          setOver(false);
          onFiles(event.dataTransfer.files);
        }}
        className={cn(
          "flex min-h-28 cursor-pointer flex-col items-center justify-center gap-1 border-2 border-dashed px-4 py-6 text-center transition-colors",
          over ? "border-accent bg-accent-subtle" : "border-line-strong bg-surface hover:border-ink",
        )}
      >
        <svg aria-hidden="true" viewBox="0 0 24 24" className="size-7 text-ink-secondary" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M4 16.5V19a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-2.5M12 4v11M7.5 8.5 12 4l4.5 4.5" strokeLinecap="square" />
        </svg>
        <span className="font-medium">{count === 0 ? "Fotos hierher ziehen oder auswählen" : "Weitere Fotos dazu"}</span>
        <span className="text-hint text-ink-tertiary">JPEG, PNG, WebP oder HEIC. Das erste ist das Hauptbild.</span>
        <input id={`${id}-pick`} type="file" accept={IMAGE_PICKER_ACCEPT} multiple className="sr-only" onChange={(event) => onFiles(event.target.files)} />
      </label>
      <label
        htmlFor={`${id}-camera`}
        className="flex cursor-pointer items-center justify-center gap-2 border border-line-control bg-canvas px-4 py-3 font-medium hover:border-ink sm:hidden"
      >
        <svg aria-hidden="true" viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M3 8h4l2-3h6l2 3h4v11H3z" strokeLinejoin="miter" />
          <circle cx="12" cy="13" r="3.5" />
        </svg>
        Foto aufnehmen
        <input id={`${id}-camera`} type="file" accept="image/*" capture="environment" className="sr-only" onChange={(event) => onFiles(event.target.files)} />
      </label>
    </div>
  );
}
