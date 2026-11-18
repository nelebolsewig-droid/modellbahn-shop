"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { FormError } from "@/components/forms/form-error";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { setMediaStudioForAll } from "@/lib/api/generated/admin-media/admin-media";
import { isApiProblem } from "@/lib/api/problem";
import { errorMessage } from "@/lib/i18n/problems";

/** What the dialog says once the worker has taken the photos over. */
export function switchedMessage(count: number): string {
  if (count === 0) {
    return "Alle Fotos stehen schon im Fotostudio.";
  }
  return count === 1
    ? "1 Foto wird jetzt neu gerechnet."
    : `${count} Fotos werden jetzt neu gerechnet, eines nach dem anderen. Das dauert einige Sekunden je Foto.`;
}

/**
 * Sends every photo of the shop through the photo studio at once (ADR 0031). The
 * originals stay, and each photo keeps its own switch in its gallery.
 */
export function StudioForAll() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const switchAll = useMutation({
    mutationFn: () => setMediaStudioForAll({ enabled: true }),
    // Every product shows its photos: all of them may be on their way now.
    onSuccess: () => queryClient.invalidateQueries(),
  });
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          switchAll.reset();
        }
      }}
    >
      <DialogTrigger asChild>
        <Button type="button" variant="ghost" size="sm">
          Alle Fotos umstellen …
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogTitle>Alle Fotos ins Fotostudio schicken?</DialogTitle>
        <DialogDescription>
          Jedes Foto im Shop wird freigestellt, in Licht und Farbe angeglichen und auf die gemeinsame Standlinie
          gestellt, auch die Fotos der anderen Modelle. Die Originale bleiben erhalten: Bei jedem Foto lässt sich das
          Fotostudio danach einzeln wieder abschalten.
        </DialogDescription>
        {switchAll.isSuccess ? (
          <p role="status" className="mt-4 text-small text-success">
            {switchedMessage(switchAll.data.switched)}
          </p>
        ) : null}
        <FormError
          message={
            switchAll.isError
              ? isApiProblem(switchAll.error)
                ? errorMessage(switchAll.error)
                : "Die Fotos ließen sich nicht umstellen."
              : undefined
          }
          className="mt-4"
        />
        <div className="mt-6 flex flex-wrap justify-end gap-3">
          <DialogClose asChild>
            <Button type="button" variant="secondary">
              {switchAll.isSuccess ? "Schließen" : "Abbrechen"}
            </Button>
          </DialogClose>
          {switchAll.isSuccess ? null : (
            <Button
              type="button"
              disabled={switchAll.isPending}
              aria-busy={switchAll.isPending || undefined}
              onClick={() => switchAll.mutate()}
            >
              {switchAll.isPending ? "Stellt um …" : "Alle umstellen"}
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
