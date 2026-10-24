"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { FormError } from "@/components/forms/form-error";
import { ResultPanel } from "@/components/forms/result-panel";
import { SubmitButton } from "@/components/forms/submit-button";
import { FormField } from "@/components/ui/form-field";
import { PasswordInput } from "@/components/ui/password-input";
import { TextLink } from "@/components/ui/text-link";
import { useVerifyCustomerEmail } from "@/lib/api/generated/store-account/store-account";
import { useApiForm } from "@/lib/forms/use-api-form";
import { CUSTOMER_AREA } from "@/lib/navigation";
import { useCustomerSessionCache } from "@/lib/session/customer";
import { emailVerificationSchema } from "@/lib/validation/account";

const NEW_LINK = (
  <p>
    <TextLink href="/konto/bestaetigung-erneut">Neuen Bestätigungslink anfordern</TextLink>
  </p>
);

/**
 * Redeems the token from the verification e-mail together with the password chosen
 * at registration, so that a link opened by someone else cannot hand them the
 * account. Success logs the customer in (the API sets the session cookie) and leads
 * to "Mein Konto".
 */
export function VerifyEmail({ token }: { token: string | null }) {
  if (token === null) {
    return (
      <ResultPanel tone="danger" title="Der Link ist unvollständig">
        <p>Bitte öffne den Link direkt aus der E-Mail. Wenn das nicht klappt, schicken wir dir einen neuen.</p>
        {NEW_LINK}
      </ResultPanel>
    );
  }
  return <VerificationForm token={token} />;
}

function VerificationForm({ token }: { token: string }) {
  const router = useRouter();
  const cache = useCustomerSessionCache();
  const verify = useVerifyCustomerEmail();
  const [verified, setVerified] = useState(false);
  const { form, onSubmit, formError } = useApiForm({
    schema: emailVerificationSchema,
    defaultValues: { password: "" },
    codeFields: { invalid_password: "password" },
    async submit(values) {
      const account = await verify.mutateAsync({ data: { token, password: values.password } });
      setVerified(true);
      cache.store(account);
      router.replace(CUSTOMER_AREA.home);
    },
  });
  const {
    register,
    formState: { errors, isSubmitting },
  } = form;

  if (verified) {
    return (
      <ResultPanel tone="success" title="E-Mail-Adresse bestätigt">
        <p>Willkommen! Du bist jetzt angemeldet und wirst zu deinem Konto weitergeleitet.</p>
        <p>
          <TextLink href={CUSTOMER_AREA.home}>Weiter zu „Mein Konto“</TextLink>
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
        <FormField label="Dein Passwort" error={errors.password?.message}>
          {(control) => (
            <PasswordInput {...control} {...register("password")} autoComplete="current-password" />
          )}
        </FormField>
        <SubmitButton pending={isSubmitting} pendingLabel="Wird bestätigt …" className="w-full">
          E-Mail-Adresse bestätigen
        </SubmitButton>
      </div>
    </form>
  );
}
