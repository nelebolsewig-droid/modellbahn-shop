"use client";

import { useState } from "react";

import { FormError } from "@/components/forms/form-error";
import { SubmitButton } from "@/components/forms/submit-button";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { FormField } from "@/components/ui/form-field";
import { PasswordInput } from "@/components/ui/password-input";
import { useDeleteCustomerAccount } from "@/lib/api/generated/store-account/store-account";
import { useApiForm } from "@/lib/forms/use-api-form";
import { accountDeletionSchema } from "@/lib/validation/account";

/** "Konto löschen" with a confirmation dialog that asks for the password. */
export function DeleteAccount({ onDeleted }: { onDeleted: () => void }) {
  const [open, setOpen] = useState(false);
  const deletion = useDeleteCustomerAccount();
  const { form, onSubmit, formError } = useApiForm({
    schema: accountDeletionSchema,
    defaultValues: { password: "" },
    codeFields: { invalid_password: "password" },
    async submit(values) {
      await deletion.mutateAsync({ data: values });
      setOpen(false);
      onDeleted();
    },
  });
  const {
    register,
    formState: { errors, isSubmitting },
  } = form;

  function changeOpen(next: boolean) {
    setOpen(next);
    if (!next) {
      // A password typed for a dialog that was cancelled must not linger.
      form.reset();
    }
  }

  return (
    <Dialog open={open} onOpenChange={changeOpen}>
      <DialogTrigger asChild>
        <Button variant="danger">Konto löschen …</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogTitle>Konto endgültig löschen?</DialogTitle>
        <DialogDescription>
          Gib zur Bestätigung dein Passwort ein. Das Löschen lässt sich nicht rückgängig machen.
        </DialogDescription>
        <form noValidate onSubmit={onSubmit} className="mt-6">
          <FormError message={formError?.message} />
          <FormField label="Passwort" error={errors.password?.message}>
            {(control) => (
              <PasswordInput {...control} {...register("password")} autoComplete="current-password" />
            )}
          </FormField>
          <div className="mt-6 flex flex-wrap justify-end gap-3">
            <DialogClose asChild>
              <Button type="button" variant="secondary">
                Abbrechen
              </Button>
            </DialogClose>
            <SubmitButton variant="danger" pending={isSubmitting} pendingLabel="Wird gelöscht …">
              Endgültig löschen
            </SubmitButton>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
