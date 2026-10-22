"use client";

import { useState } from "react";

import { Callout } from "@/components/ui/alert";
import { FormField } from "@/components/ui/form-field";
import { PasswordInput } from "@/components/ui/password-input";
import { useApiForm } from "@/lib/forms/use-api-form";
import {
  PASSWORD_MIN_LENGTH,
  passwordChangeSchema,
  type PasswordChangeValues,
} from "@/lib/validation/account";

import { FormError } from "./form-error";
import { SubmitButton } from "./submit-button";

type PasswordChangeFormProps = {
  /** Changes the password; the API ends all other sessions of the account. */
  submit: (values: PasswordChangeValues) => Promise<void>;
};

/** Current and new password; used by customers and by staff. */
export function PasswordChangeForm({ submit }: PasswordChangeFormProps) {
  const [changed, setChanged] = useState(false);
  const { form, onSubmit, formError } = useApiForm({
    schema: passwordChangeSchema,
    defaultValues: { current_password: "", new_password: "" },
    codeFields: { invalid_password: "current_password" },
    async submit(values) {
      setChanged(false);
      await submit(values);
      form.reset();
      setChanged(true);
    },
  });
  const {
    register,
    formState: { errors, isSubmitting },
  } = form;

  return (
    <form noValidate onSubmit={onSubmit}>
      <div role="status" className="not-empty:mb-6">
        {changed ? (
          <Callout tone="success">
            Dein Passwort ist geändert. Auf allen anderen Geräten bist du jetzt abgemeldet.
          </Callout>
        ) : null}
      </div>
      <FormError message={formError?.message} />
      <div className="space-y-5">
        <FormField label="Aktuelles Passwort" error={errors.current_password?.message}>
          {(control) => (
            <PasswordInput
              {...control}
              {...register("current_password")}
              autoComplete="current-password"
            />
          )}
        </FormField>
        <FormField
          label="Neues Passwort"
          hint={`Mindestens ${PASSWORD_MIN_LENGTH} Zeichen.`}
          error={errors.new_password?.message}
        >
          {(control) => (
            <PasswordInput {...control} {...register("new_password")} autoComplete="new-password" />
          )}
        </FormField>
        <SubmitButton pending={isSubmitting} pendingLabel="Wird gespeichert …">
          Passwort ändern
        </SubmitButton>
      </div>
    </form>
  );
}
