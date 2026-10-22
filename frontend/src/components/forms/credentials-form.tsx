"use client";

import type { ReactNode } from "react";

import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { useApiForm } from "@/lib/forms/use-api-form";
import { loginSchema, type LoginValues } from "@/lib/validation/account";

import { FormError } from "./form-error";
import { SubmitButton } from "./submit-button";

type CredentialsFormProps = {
  /** Logs in; a thrown ApiProblem is shown in the form. */
  submit: (values: LoginValues) => Promise<void>;
  submitLabel: string;
  /** A way out for some errors, chosen by problem code (e.g. `email_not_verified`). */
  errorHelp?: (code: string) => ReactNode;
};

/** E-mail address and password: the login form of the shop and of the admin area. */
export function CredentialsForm({ submit, submitLabel, errorHelp }: CredentialsFormProps) {
  const { form, onSubmit, formError } = useApiForm({
    schema: loginSchema,
    defaultValues: { email: "", password: "" },
    submit,
  });
  const {
    register,
    formState: { errors, isSubmitting },
  } = form;

  return (
    <form noValidate onSubmit={onSubmit}>
      <FormError message={formError?.message}>
        {formError && errorHelp ? errorHelp(formError.code) : null}
      </FormError>
      <div className="space-y-5">
        <FormField label="E-Mail-Adresse" error={errors.email?.message}>
          {(control) => (
            <Input
              {...control}
              {...register("email")}
              type="email"
              inputMode="email"
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
            />
          )}
        </FormField>
        <FormField label="Passwort" error={errors.password?.message}>
          {(control) => (
            <PasswordInput {...control} {...register("password")} autoComplete="current-password" />
          )}
        </FormField>
        <SubmitButton pending={isSubmitting} pendingLabel="Anmeldung läuft …" className="w-full">
          {submitLabel}
        </SubmitButton>
      </div>
    </form>
  );
}
