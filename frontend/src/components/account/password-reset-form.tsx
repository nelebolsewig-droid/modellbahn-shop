"use client";

import { useState } from "react";

import { FormError } from "@/components/forms/form-error";
import { ResultPanel } from "@/components/forms/result-panel";
import { SubmitButton } from "@/components/forms/submit-button";
import { FormField } from "@/components/ui/form-field";
import { PasswordInput } from "@/components/ui/password-input";
import { TextLink } from "@/components/ui/text-link";
import { useConfirmPasswordReset } from "@/lib/api/generated/store-account/store-account";
import { useApiForm } from "@/lib/forms/use-api-form";
import { useCustomerSessionCache } from "@/lib/session/customer";
import { PASSWORD_MIN_LENGTH, passwordResetSchema } from "@/lib/validation/account";

const NEW_LINK = (
  <p>
    <TextLink href="/konto/passwort-vergessen">Neuen Link anfordern</TextLink>
  </p>
);

/** Sets a new password with the token from the reset e-mail. */
export function PasswordResetForm({ token }: { token: string | null }) {
  if (token === null) {
    return (
      <ResultPanel tone="danger" title="Der Link ist unvollständig">
        <p>Bitte öffne den Link direkt aus der E-Mail oder fordere einen neuen an.</p>
        {NEW_LINK}
      </ResultPanel>
    );
  }
  return <NewPasswordForm token={token} />;
}

function NewPasswordForm({ token }: { token: string }) {
  const confirm = useConfirmPasswordReset();
  const cache = useCustomerSessionCache();
  const [done, setDone] = useState(false);
  const { form, onSubmit, formError } = useApiForm({
    schema: passwordResetSchema,
    defaultValues: { new_password: "" },
    async submit(values) {
      await confirm.mutateAsync({ data: { token, new_password: values.new_password } });
      // The API ended every session of the account, including one in this browser.
      cache.clear();
      setDone(true);
    },
  });
  const {
    register,
    formState: { errors, isSubmitting },
  } = form;

  if (done) {
    return (
      <ResultPanel tone="success" title="Neues Passwort gespeichert">
        <p>Zur Sicherheit haben wir dich auf allen Geräten abgemeldet.</p>
        <p>
          <TextLink href="/konto/anmelden">Jetzt anmelden</TextLink>
        </p>
      </ResultPanel>
    );
  }

  return (
    <form noValidate onSubmit={onSubmit}>
      <FormError message={formError?.message}>
        {formError?.code === "invalid_token" ? NEW_LINK : null}
      </FormError>
      <div className="space-y-5">
        <FormField
          label="Neues Passwort"
          hint={`Mindestens ${PASSWORD_MIN_LENGTH} Zeichen.`}
          error={errors.new_password?.message}
        >
          {(control) => (
            <PasswordInput {...control} {...register("new_password")} autoComplete="new-password" />
          )}
        </FormField>
        <SubmitButton pending={isSubmitting} pendingLabel="Wird gespeichert …" className="w-full">
          Passwort speichern
        </SubmitButton>
      </div>
    </form>
  );
}
