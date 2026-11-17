"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { AdminShell } from "@/components/admin/admin-shell";
import { Panel } from "@/components/admin/panel";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { PendingNotice } from "@/components/ui/pending-notice";
import {
  getGetProductionQueryKey,
  useChangeProduction,
  useGetProduction,
} from "@/lib/api/generated/admin-catalog/admin-catalog";
import type { StaffRole } from "@/lib/api/generated/model";
import { errorMessage, fieldErrorMessage } from "@/lib/i18n/problems";
import { leadTimeText } from "@/lib/sales/availability";
import { leadTimeSchema } from "@/lib/validation/catalog";

import { SettingsBackLink } from "./settings-page";

/** The page: the shop's lead time, changed by the owner (ADR 0029). */
export function LeadTimeSettingsPage() {
  return (
    <AdminShell>
      {({ staff }) => (
        <>
          <SettingsBackLink />
          <h1 className="mt-6 mb-8 text-heading sm:text-title">Lieferzeit</h1>
          <LeadTimeSettings staffRole={staff.role} />
        </>
      )}
    </AdminShell>
  );
}

/**
 * How long making a piece takes when the shelf runs short: one lead time for every model
 * that has none of its own. Changing it changes them all at once, in the shop too.
 */
export function LeadTimeSettings({ staffRole }: { staffRole: StaffRole }) {
  const production = useGetProduction();
  if (production.isPending) {
    return <PendingNotice>Wird geladen …</PendingNotice>;
  }
  if (production.isError) {
    return <p className="text-small text-danger">{errorMessage(production.error)}</p>;
  }
  const weeks = [production.data.default_lead_time_min_weeks, production.data.default_lead_time_max_weeks] as const;
  return (
    <Panel title="Lieferzeit fürs Nachfertigen" code="EIN 04">
      <p className="max-w-2xl text-small text-ink-secondary">
        Fehlt ein Modell im Regal, fertigt die Werkstatt es nach. Der Shop nennt dann diese Lieferzeit, bei jedem
        Modell ohne eigene. Eine eigene Lieferzeit oder „nicht nachfertigen“ stellt man beim Modell ein. eBay verkauft
        weiter nur, was im Regal liegt.
      </p>
      {staffRole === "owner" ? (
        <LeadTimeForm weeks={weeks} />
      ) : (
        <p className="mt-6 text-body">
          Jetzt: <span className="font-medium">{leadTimeText(weeks)}</span>. Ändern kann sie nur der Inhaber.
        </p>
      )}
    </Panel>
  );
}

function LeadTimeForm({ weeks }: { weeks: readonly [number, number] }) {
  const queryClient = useQueryClient();
  const [min, setMin] = useState(String(weeks[0]));
  const [max, setMax] = useState(String(weeks[1]));
  const [problem, setProblem] = useState<string | undefined>(undefined);
  const change = useChangeProduction({
    mutation: {
      onSuccess(saved) {
        queryClient.setQueryData(getGetProductionQueryKey(), saved);
      },
    },
  });
  const fieldError = change.error?.fieldErrors[0];

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsed = leadTimeSchema.safeParse({ min, max });
    if (!parsed.success) {
      setProblem(parsed.error.issues[0]?.message);
      return;
    }
    setProblem(undefined);
    change.mutate({ data: { default_lead_time_min_weeks: parsed.data.min, default_lead_time_max_weeks: parsed.data.max } });
  }

  const message =
    problem ??
    (fieldError ? fieldErrorMessage(fieldError.field, fieldError.code) : change.isError ? errorMessage(change.error) : undefined);
  return (
    <form noValidate onSubmit={submit} aria-label="Lieferzeit ändern" className="mt-6">
      <div className="flex flex-wrap items-end gap-3">
        <FormField label="Von (Wochen)">
          {(control) => (
            <Input {...control} value={min} onChange={(event) => setMin(event.target.value)} inputMode="numeric" className="w-20" />
          )}
        </FormField>
        <FormField label="Bis (Wochen)">
          {(control) => (
            <Input {...control} value={max} onChange={(event) => setMax(event.target.value)} inputMode="numeric" className="w-20" />
          )}
        </FormField>
        <Button type="submit" disabled={change.isPending} aria-busy={change.isPending || undefined} className="mb-[1.375rem]">
          {change.isPending ? "Speichert …" : "Speichern"}
        </Button>
      </div>
      <p role="alert" className="text-small font-medium text-danger empty:hidden">
        {message}
      </p>
      <p role="status" className="text-small text-success empty:hidden">
        {change.isSuccess && message === undefined
          ? `Gespeichert. Jedes Modell ohne eigene Lieferzeit zeigt jetzt ${leadTimeText([
              change.data.default_lead_time_min_weeks,
              change.data.default_lead_time_max_weeks,
            ])}.`
          : null}
      </p>
    </form>
  );
}
