"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Panel } from "@/components/admin/panel";
import { FormError } from "@/components/forms/form-error";
import { SubmitButton } from "@/components/forms/submit-button";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { PendingNotice } from "@/components/ui/pending-notice";
import { StatusBadge } from "@/components/ui/status-badge";
import { Textarea } from "@/components/ui/textarea";
import {
  announceFair,
  createFair,
  deleteFair,
  getFairNewsCounts,
  listAdminFairs,
  updateFair,
} from "@/lib/api/generated/admin-site/admin-site";
import type { AdminFairOut, AnnouncementOut, SubscriptionCountsOut } from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";
import { formatLongDate } from "@/lib/format";
import { useApiForm } from "@/lib/forms/use-api-form";
import { errorMessage } from "@/lib/i18n/problems";
import { place, todayInGermany } from "@/lib/site/fairs";
import { EMPTY_FAIR, fairSchema, type FairValues } from "@/lib/validation/site";

export const FAIRS_KEY = ["admin", "fairs"] as const;
export const FAIR_NEWS_KEY = ["admin", "fair-news"] as const;

function useRefresh() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: FAIRS_KEY });
    void queryClient.invalidateQueries({ queryKey: FAIR_NEWS_KEY });
  };
}

/** The coming fairs first (soonest on top), then the past ones (latest on top). */
export function splitFairs(fairs: readonly AdminFairOut[], today: string) {
  const upcoming = fairs.filter((fair) => fair.ends_on >= today).sort((a, b) => a.starts_on.localeCompare(b.starts_on));
  const past = fairs.filter((fair) => fair.ends_on < today).sort((a, b) => b.starts_on.localeCompare(a.starts_on));
  return { upcoming, past };
}

/**
 * The fairs of the shop's "Termine" page: create, change, publish and announce them
 * to the fair news. An announcement goes out once per fair, to every confirmed
 * subscriber, by the worker.
 */
export function FairsManager() {
  const fairs = useQuery<AdminFairOut[], ApiProblem>({
    queryKey: FAIRS_KEY,
    queryFn: async ({ signal }) => (await listAdminFairs({ signal })).items,
  });
  const counts = useQuery<SubscriptionCountsOut, ApiProblem>({
    queryKey: FAIR_NEWS_KEY,
    queryFn: ({ signal }) => getFairNewsCounts({ signal }),
  });
  const today = todayInGermany();

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_24rem]">
      <Panel title="Messen" code="MES 01">
        {fairs.isPending ? (
          <PendingNotice>Messen werden geladen …</PendingNotice>
        ) : fairs.isError ? (
          <p role="alert" className="text-small text-danger">
            {errorMessage(fairs.error)}
          </p>
        ) : fairs.data.length === 0 ? (
          <p className="text-small text-ink-secondary">
            Noch keine Messe eingetragen. Leg rechts die erste an; der Shop zeigt sie unter „Termine“.
          </p>
        ) : (
          <FairList fairs={fairs.data} today={today} recipients={counts.data?.confirmed ?? null} />
        )}
      </Panel>
      <div className="space-y-6">
        <Panel title="Messe-Post" code="MES 02">
          {counts.isError ? (
            <p role="alert" className="text-small text-danger">
              {errorMessage(counts.error)}
            </p>
          ) : (
            <>
              <p className="flex items-baseline gap-3">
                <span className="text-title font-extralight tabular-nums">{counts.data?.confirmed ?? "–"}</span>
                <span className="text-small text-ink-secondary">bestätigte Empfänger</span>
              </p>
              <p className="mt-2 text-hint text-ink-tertiary">
                {counts.data ? `${counts.data.pending} warten noch auf ihren Bestätigungslink. ` : null}
                Unbestätigte Anmeldungen verfallen nach sieben Tagen.
              </p>
            </>
          )}
        </Panel>
        <Panel title="Neue Messe" code="MES 03">
          <NewFair />
        </Panel>
      </div>
    </div>
  );
}

function NewFair() {
  const refresh = useRefresh();
  return <FairForm onDone={refresh} />;
}

function FairList({
  fairs,
  today,
  recipients,
}: {
  fairs: readonly AdminFairOut[];
  today: string;
  recipients: number | null;
}) {
  const { upcoming, past } = splitFairs(fairs, today);
  return (
    <div className="space-y-8">
      {upcoming.length > 0 ? (
        <section aria-label="Kommende Messen">
          <h3 className="label-caps text-ink-tertiary">Kommend</h3>
          <ul className="mt-2 divide-y divide-line">
            {upcoming.map((fair) => (
              <FairRow key={fair.id} fair={fair} past={false} recipients={recipients} />
            ))}
          </ul>
        </section>
      ) : null}
      {past.length > 0 ? (
        <section aria-label="Vergangene Messen">
          <h3 className="label-caps text-ink-tertiary">Vorbei</h3>
          <ul className="mt-2 divide-y divide-line">
            {past.map((fair) => (
              <FairRow key={fair.id} fair={fair} past recipients={recipients} />
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

function FairRow({ fair, past, recipients }: { fair: AdminFairOut; past: boolean; recipients: number | null }) {
  const refresh = useRefresh();
  const [editing, setEditing] = useState(false);
  const remove = useMutation<void, ApiProblem>({
    mutationFn: () => deleteFair(fair.id),
    onSuccess: refresh,
  });

  if (editing) {
    return (
      <li className="py-5">
        <FairForm
          fair={fair}
          onDone={() => {
            setEditing(false);
            refresh();
          }}
          onCancel={() => setEditing(false)}
        />
      </li>
    );
  }

  const announceable = fair.published && fair.announced_at === null && !past;
  return (
    <li className="grid gap-x-6 gap-y-3 py-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start">
      <div className="min-w-0">
        <p className="font-mono text-hint text-ink-tertiary">{fair.when}</p>
        <p className={past ? "mt-1 font-medium text-ink-secondary" : "mt-1 font-medium"}>{fair.name}</p>
        <p className="mt-0.5 text-small text-ink-secondary">
          {place(fair)}
          {fair.booth ? ` · ${fair.booth}` : ""}
        </p>
        <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
          {fair.published ? (
            <StatusBadge tone="success">Im Shop</StatusBadge>
          ) : (
            <StatusBadge tone="neutral">Entwurf</StatusBadge>
          )}
          {fair.announced_at !== null ? (
            <StatusBadge tone="accent">{`Angekündigt am ${formatLongDate(new Date(fair.announced_at))}`}</StatusBadge>
          ) : null}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-1 sm:justify-end">
        {announceable ? <AnnounceButton fair={fair} recipients={recipients} /> : null}
        <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(true)}>
          Bearbeiten
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="text-danger hover:bg-danger-subtle hover:text-danger"
          disabled={remove.isPending}
          onClick={() => {
            if (window.confirm(`Messe „${fair.name}“ löschen?`)) {
              remove.mutate();
            }
          }}
        >
          Löschen
        </Button>
        <span role="alert" className="w-full text-hint text-danger empty:hidden sm:text-right">
          {remove.isError ? errorMessage(remove.error) : null}
        </span>
      </div>
    </li>
  );
}

function AnnounceButton({ fair, recipients }: { fair: AdminFairOut; recipients: number | null }) {
  const refresh = useRefresh();
  const [open, setOpen] = useState(false);
  // The list reloads only once the dialog closes: an announced fair loses this button,
  // and the dialog with its answer would vanish along with it.
  const announce = useMutation<AnnouncementOut, ApiProblem>({ mutationFn: () => announceFair(fair.id) });
  const nobody = recipients === 0;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          if (announce.isSuccess) {
            refresh();
          }
          announce.reset();
        }
      }}
    >
      <Button type="button" size="sm" onClick={() => setOpen(true)}>
        Ankündigen
      </Button>
      <DialogContent>
        <DialogTitle>Messe ankündigen?</DialogTitle>
        {announce.isSuccess ? (
          <>
            <DialogDescription>
              Die Ankündigung geht jetzt an{" "}
              {announce.data.recipients === 1 ? "einen Empfänger" : `${announce.data.recipients} Empfänger`} hinaus.
            </DialogDescription>
            <div className="mt-6 flex justify-end">
              <DialogClose asChild>
                <Button type="button" size="sm">
                  Fertig
                </Button>
              </DialogClose>
            </div>
          </>
        ) : (
          <>
            <DialogDescription>
              {nobody
                ? "Noch hat niemand die Messe-Post bestätigt. Sobald sich jemand angemeldet hat, kannst du die Messe ankündigen."
                : `„${fair.name}“ geht per E-Mail an ${
                    recipients === null ? "alle" : recipients === 1 ? "einen" : recipients
                  } bestätigte${recipients === 1 ? "n" : ""} Empfänger der Messe-Post. Jede Messe lässt sich nur einmal ankündigen.`}
            </DialogDescription>
            {announce.isError ? (
              <p role="alert" className="mt-4 text-small text-danger">
                {errorMessage(announce.error)}
              </p>
            ) : null}
            <div className="mt-6 flex flex-wrap justify-end gap-3">
              <DialogClose asChild>
                <Button type="button" variant="secondary" size="sm">
                  Abbrechen
                </Button>
              </DialogClose>
              <Button
                type="button"
                size="sm"
                disabled={nobody || announce.isPending}
                aria-busy={announce.isPending || undefined}
                onClick={() => announce.mutate()}
              >
                {announce.isPending ? "Wird gesendet …" : "Jetzt senden"}
              </Button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function valuesOf(fair: AdminFairOut): FairValues {
  return {
    name: fair.name,
    starts_on: fair.starts_on,
    ends_on: fair.ends_on,
    venue: fair.venue,
    street: fair.street,
    postal_code: fair.postal_code,
    city: fair.city,
    booth: fair.booth,
    hours: fair.hours,
    website_url: fair.website_url,
    note: fair.note,
    published: fair.published,
  };
}

type FairFormProps = {
  /** The fair to change; absent for a new one. */
  fair?: AdminFairOut;
  onDone: () => void;
  onCancel?: () => void;
};

function FairForm({ fair, onDone, onCancel }: FairFormProps) {
  const { form, onSubmit, formError } = useApiForm({
    schema: fairSchema,
    defaultValues: fair ? valuesOf(fair) : EMPTY_FAIR,
    async submit(values) {
      if (fair) {
        await updateFair(fair.id, values);
      } else {
        await createFair(values);
        form.reset(EMPTY_FAIR);
      }
      onDone();
    },
  });
  const {
    register,
    getValues,
    setValue,
    formState: { errors, isSubmitting },
  } = form;

  return (
    <form noValidate onSubmit={onSubmit} aria-label={fair ? `Messe ${fair.name} bearbeiten` : "Neue Messe"}>
      <FormError message={formError?.message} className="mb-4" />
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField label="Name" error={errors.name?.message} className="sm:col-span-2">
          {(control) => <Input {...control} {...register("name")} maxLength={120} />}
        </FormField>
        <FormField label="Erster Tag" error={errors.starts_on?.message}>
          {(control) => (
            <Input
              {...control}
              type="date"
              {...register("starts_on", {
                // A one-day fair is the usual case: the last day follows the first.
                onChange: (event: { target: { value: string } }) => {
                  const end = getValues("ends_on");
                  if (!end || end < event.target.value) {
                    setValue("ends_on", event.target.value, { shouldValidate: end !== "" });
                  }
                },
              })}
            />
          )}
        </FormField>
        <FormField label="Letzter Tag" error={errors.ends_on?.message}>
          {(control) => <Input {...control} type="date" {...register("ends_on")} />}
        </FormField>
        <FormField label="Ort" hint="Halle, Kulturhaus, Hotel …" error={errors.venue?.message} className="sm:col-span-2">
          {(control) => <Input {...control} {...register("venue")} maxLength={120} />}
        </FormField>
        <FormField label="Straße" error={errors.street?.message} className="sm:col-span-2">
          {(control) => <Input {...control} {...register("street")} maxLength={120} autoComplete="off" />}
        </FormField>
        <FormField label="PLZ" error={errors.postal_code?.message}>
          {(control) => <Input {...control} {...register("postal_code")} maxLength={10} inputMode="numeric" />}
        </FormField>
        <FormField label="Stadt" error={errors.city?.message}>
          {(control) => <Input {...control} {...register("city")} maxLength={80} />}
        </FormField>
        <FormField label="Unser Stand" hint="z. B. Halle 3, Stand L04" error={errors.booth?.message}>
          {(control) => <Input {...control} {...register("booth")} maxLength={60} />}
        </FormField>
        <FormField label="Website der Messe" error={errors.website_url?.message}>
          {(control) => <Input {...control} type="url" inputMode="url" {...register("website_url")} placeholder="https://" />}
        </FormField>
        <FormField
          label="Öffnungszeiten"
          hint="Eine Zeile pro Tag, z. B. Sa 10–18 Uhr"
          error={errors.hours?.message}
          className="sm:col-span-2"
        >
          {(control) => <Textarea {...control} {...register("hours")} rows={3} className="min-h-20" />}
        </FormField>
        <FormField label="Hinweis" hint="Erscheint unter dem Termin" error={errors.note?.message} className="sm:col-span-2">
          {(control) => <Textarea {...control} {...register("note")} rows={2} className="min-h-16" />}
        </FormField>
      </div>
      <label className="mt-5 flex items-center gap-3 text-small">
        <input type="checkbox" {...register("published")} className="size-4 accent-[var(--selected)]" />
        Im Shop unter „Termine“ zeigen
      </label>
      <div className="mt-5 flex flex-wrap gap-3">
        <SubmitButton pending={isSubmitting} pendingLabel="Speichert …" size="sm">
          {fair ? "Speichern" : "Messe anlegen"}
        </SubmitButton>
        {onCancel ? (
          <Button type="button" variant="secondary" size="sm" onClick={onCancel}>
            Abbrechen
          </Button>
        ) : null}
      </div>
    </form>
  );
}
