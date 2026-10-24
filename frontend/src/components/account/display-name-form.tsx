"use client";

import { useState } from "react";

import { FormError } from "@/components/forms/form-error";
import { SubmitButton } from "@/components/forms/submit-button";
import { Callout } from "@/components/ui/alert";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { useUpdateCustomerAccount } from "@/lib/api/generated/store-account/store-account";
import { useApiForm } from "@/lib/forms/use-api-form";
import { useCustomerSessionCache } from "@/lib/session/customer";
import { displayNameSchema } from "@/lib/validation/account";

export function DisplayNameForm({ displayName }: { displayName: string }) {
  const update = useUpdateCustomerAccount();
  const cache = useCustomerSessionCache();
  const [saved, setSaved] = useState(false);
  const { form, onSubmit, formError } = useApiForm({
    schema: displayNameSchema,
    defaultValues: { display_name: displayName },
    async submit(values) {
      setSaved(false);
      const account = await update.mutateAsync({ data: values });
      cache.store(account);
      // Shows the name as the API normalised it (e.g. without double spaces).
      form.reset({ display_name: account.display_name });
      setSaved(true);
    },
  });
  const {
    register,
    formState: { errors, isSubmitting },
  } = form;

  return (
    <form noValidate onSubmit={onSubmit}>
      <div role="status" className="not-empty:mb-6">
        {saved ? <Callout tone="success">Dein Name ist gespeichert.</Callout> : null}
      </div>
      <FormError message={formError?.message} />
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
        <FormField label="Name" error={errors.display_name?.message} className="flex-1">
          {(control) => <Input {...control} {...register("display_name")} autoComplete="name" />}
        </FormField>
        <SubmitButton pending={isSubmitting} pendingLabel="Speichert …" className="sm:mt-6.5">
          Speichern
        </SubmitButton>
      </div>
    </form>
  );
}
