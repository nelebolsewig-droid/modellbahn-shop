"use client";

import { useState } from "react";

import { FormError } from "@/components/forms/form-error";
import { ResultPanel } from "@/components/forms/result-panel";
import { SubmitButton } from "@/components/forms/submit-button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { TextLink } from "@/components/ui/text-link";
import { useRegisterCustomer } from "@/lib/api/generated/store-account/store-account";
import { useApiForm } from "@/lib/forms/use-api-form";
import { PASSWORD_MIN_LENGTH, registrationSchema } from "@/lib/validation/account";

export function RegistrationForm() {
  const registration = useRegisterCustomer();
  const [sentTo, setSentTo] = useState<string | null>(null);
  const { form, onSubmit, formError } = useApiForm({
    schema: registrationSchema,
    defaultValues: { display_name: "", email: "", password: "" },
    async submit(values) {
      await registration.mutateAsync({ data: values });
      setSentTo(values.email);
    },
  });
  const {
    register,
    formState: { errors, isSubmitting },
  } = form;

  if (sentTo !== null) {
    // The API answers the same whether or not the address already has an account
    // (no enumeration); the e-mail tells the two cases apart.
    return (
      <ResultPanel tone="success" title="Bitte schau in dein Postfach">
        <p>
          Wir haben eine E-Mail an <strong className="break-all">{sentTo}</strong> geschickt. Darin
          steht, wie es weitergeht. Der Link zum Bestätigen ist 24 Stunden gültig.
        </p>
        <p>
          Keine E-Mail bekommen? Sieh im Spam-Ordner nach oder{" "}
          <TextLink href="/konto/bestaetigung-erneut">fordere den Link neu an</TextLink>.
        </p>
      </ResultPanel>
    );
  }

  return (
    <form noValidate onSubmit={onSubmit}>
      <FormError message={formError?.message} />
      <div className="space-y-5">
        <FormField
          label="Name"
          hint="So sprechen wir dich an, zum Beispiel in E-Mails."
          error={errors.display_name?.message}
        >
          {(control) => <Input {...control} {...register("display_name")} autoComplete="name" />}
        </FormField>
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
        <FormField
          label="Passwort"
          hint={`Mindestens ${PASSWORD_MIN_LENGTH} Zeichen. Ein ganzer Satz lässt sich gut merken.`}
          error={errors.password?.message}
        >
          {(control) => (
            <PasswordInput {...control} {...register("password")} autoComplete="new-password" />
          )}
        </FormField>
        <SubmitButton pending={isSubmitting} pendingLabel="Wird gesendet …" className="w-full">
          Konto anlegen
        </SubmitButton>
      </div>
    </form>
  );
}
