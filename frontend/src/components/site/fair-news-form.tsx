"use client";

import { useState } from "react";

import { FormError } from "@/components/forms/form-error";
import { ResultPanel } from "@/components/forms/result-panel";
import { SubmitButton } from "@/components/forms/submit-button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { TextLink } from "@/components/ui/text-link";
import { useSubscribeFairNews } from "@/lib/api/generated/store-site/store-site";
import { SHOP_NAME } from "@/lib/config";
import { useApiForm } from "@/lib/forms/use-api-form";
import { fairNewsSchema } from "@/lib/validation/site";

/**
 * Sign-up for the fair news with double opt-in: the API mails a link, and only that
 * link confirms. The answer is the same for every address, so the form never tells
 * whether someone is on the list already.
 *
 * The consent text is version "messe-post-2026-10" (CONSENT_VERSION in the backend's
 * site/domain/model.py); a change of its meaning needs a new version there.
 */
export function FairNewsForm() {
  const subscribe = useSubscribeFairNews();
  const [sentTo, setSentTo] = useState<string | null>(null);
  const { form, onSubmit, formError } = useApiForm({
    schema: fairNewsSchema,
    defaultValues: { email: "", consent: false },
    async submit(values) {
      await subscribe.mutateAsync({ data: values });
      setSentTo(values.email);
    },
  });
  const {
    register,
    formState: { errors, isSubmitting },
  } = form;

  if (sentTo !== null) {
    return (
      <ResultPanel tone="success" title="Fast geschafft – bitte bestätige noch">
        <p>
          Wir haben dir an <strong className="break-all">{sentTo}</strong> einen Link geschickt. Erst wenn du
          ihn anklickst, bekommst du die Messe-Post. Er ist sieben Tage gültig.
        </p>
        <p className="mt-2">Ist die Adresse schon eingetragen, bleibt alles, wie es ist.</p>
      </ResultPanel>
    );
  }

  return (
    <form noValidate onSubmit={onSubmit} aria-label="Messe-Post bestellen">
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
        <div>
          <label className="flex items-start gap-3 text-small leading-6">
            <input
              type="checkbox"
              {...register("consent")}
              aria-invalid={errors.consent ? true : undefined}
              aria-describedby={errors.consent ? "messe-post-zustimmung-fehler" : undefined}
              className="mt-1 size-4 shrink-0 accent-[var(--selected)]"
            />
            <span>
              Ja, schickt mir eine E-Mail, wenn <span className="whitespace-nowrap">{SHOP_NAME}</span> eine neue
              Messe ankündigt. Abmelden kann ich mich
              jederzeit mit dem Link in jeder Mail. Mehr dazu im <TextLink href="/datenschutz">Datenschutz</TextLink>.
            </span>
          </label>
          {errors.consent?.message ? (
            <p id="messe-post-zustimmung-fehler" className="mt-2 text-hint text-danger">
              {errors.consent.message}
            </p>
          ) : null}
        </div>
        <SubmitButton pending={isSubmitting} pendingLabel="Wird gesendet …" className="w-full">
          Messe-Post bestellen
        </SubmitButton>
      </div>
    </form>
  );
}
