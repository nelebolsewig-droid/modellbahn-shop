"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
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
import { deleteProduct } from "@/lib/api/generated/admin-catalog/admin-catalog";
import type { ProductOut } from "@/lib/api/generated/model";
import { type ApiProblem, isApiProblem } from "@/lib/api/problem";
import { ifMatch } from "@/lib/catalog/versions";
import { errorMessage } from "@/lib/i18n/problems";

import { ADMIN_PRODUCTS_KEY, isVersionConflict, productQueryKey } from "./use-product";

/**
 * Where the general text speaks of a single scale, the delete dialog speaks of the whole
 * model: deleting it removes every scale, so the bill of materials of any one holds it back.
 */
const DELETE_MESSAGES: Readonly<Record<string, string>> = {
  product_scale_has_bom:
    "Für das Modell gibt es in der Fertigung eine Stückliste. Leere sie zuerst, dann lässt es sich löschen.",
};

function deleteErrorMessage(error: unknown): string {
  if (isApiProblem(error) && Object.hasOwn(DELETE_MESSAGES, error.code)) {
    return DELETE_MESSAGES[error.code] ?? errorMessage(error);
  }
  return errorMessage(error);
}

/**
 * The open orders that keep a product from being deleted. The problem's English detail
 * names them after the colon ("Open orders contain the product: MB-2026-00042, eBay
 * 12-34567-89012."); only the numbers are shown.
 */
export function openOrderNumbers(error: unknown): string[] {
  if (!isApiProblem(error) || error.code !== "product_in_open_orders") {
    return [];
  }
  const listed = /:\s*(.+?)\.?$/.exec(error.detail)?.[1] ?? "";
  return listed
    .split(",")
    .map((number) => number.trim())
    .filter((number) => number !== "");
}

/**
 * Deletes a model for good, e.g. a test model. Offered while it is out of the shop (draft
 * or archived); one in the shop is archived first, which also ends its eBay listings.
 */
export function DeleteProduct({ product }: { product: ProductOut }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const remove = useMutation<void, ApiProblem>({
    mutationFn: () => deleteProduct(product.id, ifMatch(product.version)),
    onSuccess() {
      void queryClient.invalidateQueries({ queryKey: ADMIN_PRODUCTS_KEY });
      router.replace("/admin/katalog");
    },
  });

  if (product.status === "active") {
    return <p className="text-hint text-ink-tertiary">Zum Löschen erst archivieren.</p>;
  }

  // Once deleted, the button stays busy until the catalogue has taken over.
  const busy = remove.isPending || remove.isSuccess;
  const orders = openOrderNumbers(remove.error);
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          remove.reset();
        }
      }}
    >
      <DialogTrigger asChild>
        <Button type="button" variant="ghost">
          Modell löschen …
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogTitle>„{product.name}“ endgültig löschen?</DialogTitle>
        <DialogDescription>
          Gelöscht werden das Modell mit allen Maßstäben, Ausführungen und der Galerie, seine nie verkauften Stücke im
          Lager samt Journal und seine eBay-Angebote, die nicht mehr online sind; die Etiketten dieser Stücke gelten
          dann nicht mehr. Bestellungen behalten Name und Preis, die Fotos bleiben in der Medienbibliothek. Das lässt
          sich nicht rückgängig machen.
        </DialogDescription>
        <FormError message={remove.isError ? deleteErrorMessage(remove.error) : undefined} className="mt-4">
          {orders.length > 0 ? (
            <ul aria-label="Offene Bestellungen" className="flex flex-wrap gap-x-4 gap-y-1 font-mono">
              {orders.map((number) => (
                <li key={number}>{number}</li>
              ))}
            </ul>
          ) : null}
          {isVersionConflict(remove.error) ? (
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => {
                remove.reset();
                void queryClient.invalidateQueries({ queryKey: productQueryKey(product.id) });
              }}
            >
              Aktuellen Stand laden
            </Button>
          ) : null}
        </FormError>
        <div className="mt-6 flex flex-wrap justify-end gap-3">
          <DialogClose asChild>
            <Button type="button" variant="secondary">
              Behalten
            </Button>
          </DialogClose>
          <Button
            type="button"
            variant="danger"
            onClick={() => remove.mutate()}
            disabled={busy}
            aria-busy={busy || undefined}
          >
            {busy ? "Wird gelöscht …" : "Endgültig löschen"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
