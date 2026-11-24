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
import { SHOP_NAME } from "@/lib/config";
import { useApiForm } from "@/lib/forms/use-api-form";
import { PASSWORD_MIN_LENGTH, registrationSchema } from "@/lib/validation/account";

type RegistrationFormProps = {
  /**
   * Name and address already known, e.g. from a guest order: only the password is
   * asked for, the two are shown as text.
   */
  preset?: { display_name: string; email: string };
  /** Label of the submit button. */
  submitLabel?: string;
};

export function RegistrationForm({ preset, submitLabel = "Konto anlegen" }: RegistrationFormProps = {}) {
  const registration = useRegisterCustomer();
  const [sentTo, setSentTo] = useState<string | null>(null);
  const { form, onSubmit, formError } = useApiForm({
    schema: registrationSchema,
    defaultValues: {
      display_name: preset?.display_name ?? "",
      email: preset?.email ?? "",
      password: "",
      newsletter: false,
    },
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
        {preset ? (
          <p className="text-small text-ink-secondary">
            Für <span className="font-medium text-ink">{preset.display_name}</span> mit{" "}
            <span className="font-medium break-all text-ink">{preset.email}</span>.
            {errors.display_name?.message || errors.email?.message ? (
              <span role="alert" className="mt-1 block text-danger">
                {errors.display_name?.message ?? errors.email?.message}
              </span>
            ) : null}
          </p>
        ) : (
          <>
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
          </>
        )}
        <FormField
          label="Passwort"
          hint={`Mindestens ${PASSWORD_MIN_LENGTH} Zeichen. Ein ganzer Satz lässt sich gut merken.`}
          error={errors.password?.message}
        >
          {(control) => (
            <PasswordInput {...control} {...register("password")} autoComplete="new-password" />
          )}
        </FormField>
        <label className="flex items-start gap-3 text-small leading-6">
          <input
            type="checkbox"
            {...register("newsletter")}
            className="mt-1 size-4 shrink-0 accent-[var(--selected)]"
          />
          <span>
            Ja, schickt mir den Newsletter von <span className="whitespace-nowrap">{SHOP_NAME}</span>: einmal im Monat die neuen Modelle und Empfehlungen passend zu meinen Käufen. Freiwillig; ich bestätige
            ihn per E-Mail und kann ihn jederzeit mit einem Klick abbestellen. Mehr dazu im{" "}
            <TextLink href="/datenschutz">Datenschutz</TextLink>.
          </span>
        </label>
        <SubmitButton pending={isSubmitting} pendingLabel="Wird gesendet …" className="w-full">
          {submitLabel}
        </SubmitButton>
      </div>
    </form>
  );
}
