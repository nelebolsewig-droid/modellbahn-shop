"use client";

import { useState, type ReactNode } from "react";

import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { useApiForm } from "@/lib/forms/use-api-form";
import { emailSchema, type EmailValues } from "@/lib/validation/account";

import { FormError } from "./form-error";
import { SubmitButton } from "./submit-button";

type EmailRequestFormProps = {
  /** Sends the request; the API answers 202 whether or not the address is known. */
  submit: (values: EmailValues) => Promise<void>;
  submitLabel: string;
  /** Replaces the form once the request is accepted. */
  renderResult: (email: string) => ReactNode;
};

/** One e-mail field: for a new verification link and for a password reset. */
export function EmailRequestForm({ submit, submitLabel, renderResult }: EmailRequestFormProps) {
  const [sentTo, setSentTo] = useState<string | null>(null);
  const { form, onSubmit, formError } = useApiForm({
    schema: emailSchema,
    defaultValues: { email: "" },
    async submit(values) {
      await submit(values);
      setSentTo(values.email);
    },
  });
  const {
    register,
    formState: { errors, isSubmitting },
  } = form;

  if (sentTo !== null) {
    return renderResult(sentTo);
  }

  return (
    <form noValidate onSubmit={onSubmit}>
      <FormError message={formError?.message} />
      <div className="space-y-5">
        <FormField label="E-Mail-Adresse" error={errors.email?.message}>
          {(control) => (
            <Input
              {...control}
              {...register("email")}
              type="email"
              inputMode="email"
              autoComplete="email"
              autoCapitalize="none"
              spellCheck={false}
            />
          )}
        </FormField>
        <SubmitButton pending={isSubmitting} pendingLabel="Wird gesendet …" className="w-full">
          {submitLabel}
        </SubmitButton>
      </div>
    </form>
  );
}
