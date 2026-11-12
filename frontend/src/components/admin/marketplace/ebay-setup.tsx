"use client";

import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { Panel } from "@/components/admin/panel";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { PendingNotice } from "@/components/ui/pending-notice";
import { Select } from "@/components/ui/select";
import { SignalLamp } from "@/components/ui/signal-lamp";
import { StatusBadge } from "@/components/ui/status-badge";
import {
  changeEbaySettings,
  connectEbay,
  disconnectEbay,
  setEbayCategories,
} from "@/lib/api/generated/admin-marketplace/admin-marketplace";
import type { CategoryMappingOut, EbayStatusOut, PoliciesOut, PolicyOptionOut } from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";
import { formatPrice } from "@/lib/catalog/format";
import { formatLongDate } from "@/lib/format";
import { errorMessage } from "@/lib/i18n/problems";
import { CALLBACK_OUTCOMES, isReady, MODE_LABELS, priceWithMarkup, READINESS_STEPS } from "@/lib/marketplace/labels";
import { cn } from "@/lib/utils";

import { AccountDeletionPanel } from "./account-deletion-panel";
import { useEbayCategories, useEbayPolicies, useEbayRefresh, useEbayStatus, useIsOwner } from "./use-ebay";

/** A shop price to show what the markup makes of it. */
const EXAMPLE_PRICE_CENTS = 4990;

/**
 * Setting eBay up, once and rarely again: the connection and the route it sets for
 * offers, the settings that shape every offer, the eBay category of each shop category
 * and eBay's notifications of closed accounts. The daily work is on the eBay page.
 */
export function EbaySetupDesk({ outcome }: { outcome: string | null }) {
  const status = useEbayStatus();
  if (status.isPending) {
    return <PendingNotice>eBay wird geladen …</PendingNotice>;
  }
  if (status.isError) {
    return (
      <Alert tone="danger" title="eBay konnte nicht geladen werden">
        <p>{errorMessage(status.error)}</p>
      </Alert>
    );
  }
  const account = status.data;
  const returned = outcome ? CALLBACK_OUTCOMES[outcome] : undefined;
  return (
    <div className="space-y-6">
      {returned ? (
        <Alert tone={returned.tone} title={returned.text}>
          {returned.tone === "success" ? (
            <p>Prüfe unten die Fahrstraße: Erst wenn alle Signale grün sind, gehen Angebote online.</p>
          ) : null}
        </Alert>
      ) : null}
      {account.mode === "off" ? (
        <Alert tone="info" title="eBay ist ausgeschaltet">
          <p>
            Der Server läuft mit <code className="font-mono">MB_EBAY_MODE=off</code>. Zum Ausprobieren eignet sich{" "}
            <code className="font-mono">test</code> (der eingebaute Testmarktplatz), für den echten Verkauf{" "}
            <code className="font-mono">production</code> mit den Schlüsseln aus eBays Entwicklerkonto.
          </p>
        </Alert>
      ) : (
        <>
          <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_24rem]">
            <ConnectionPanel account={account} />
            <SettingsPanel account={account} />
          </div>
          <CategoriesPanel />
        </>
      )}
      {/* eBay checks this endpoint before it enables the production keys: also while off. */}
      <AccountDeletionPanel />
    </div>
  );
}

// --- Connection -----------------------------------------------------------------------

function ConnectionPanel({ account }: { account: EbayStatusOut }) {
  const owner = useIsOwner();
  const refresh = useEbayRefresh();
  const connect = useMutation<string, ApiProblem>({
    mutationFn: async () => (await connectEbay()).authorize_url,
    // eBay's consent page; it sends the owner back to the callback, which leads here.
    onSuccess: (url) => window.location.assign(url),
  });
  const connected = account.status === "connected";

  return (
    <Panel
      title="Verbindung"
      code="EBY 01"
      actions={
        <StatusBadge tone={account.mode === "production" ? "success" : "accent"}>
          {MODE_LABELS[account.mode]}
        </StatusBadge>
      }
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="flex items-center gap-2 text-body font-medium">
            <SignalLamp color={connected ? "green" : account.status === "expired" ? "yellow" : "off"} />
            {connected
              ? `Verbunden als ${account.seller_name}`
              : account.status === "expired"
                ? "Die Zustimmung bei eBay ist abgelaufen"
                : "Nicht verbunden"}
          </p>
          <p className="mt-1 text-hint text-ink-tertiary">
            {connected && account.consent_expires_at
              ? `Zustimmung gilt bis ${formatLongDate(new Date(account.consent_expires_at))}. Danach einmal neu verbinden.`
              : "Beim Verbinden meldest du dich bei eBay an und erlaubst dem Shop, Angebote und Bestellungen zu verwalten."}
          </p>
        </div>
        {owner ? (
          connected ? (
            <DisconnectButton onDone={refresh} />
          ) : (
            <Button
              type="button"
              size="sm"
              disabled={connect.isPending}
              aria-busy={connect.isPending || undefined}
              onClick={() => connect.mutate()}
            >
              {connect.isPending
                ? "Weiter zu eBay …"
                : account.status === "expired"
                  ? "Neu verbinden"
                  : "Mit eBay verbinden"}
            </Button>
          )
        ) : null}
      </div>
      {connect.isError ? (
        <p role="alert" className="mt-3 text-small text-danger">
          {errorMessage(connect.error)}
        </p>
      ) : null}
      <RouteSignals account={account} />
      {!owner ? (
        <p className="mt-4 text-hint text-ink-tertiary">Verbindung und Einstellungen ändert der Inhaber.</p>
      ) : null}
    </Panel>
  );
}

/**
 * The readiness as a route on the signal-box desk: one signal per condition, the
 * route is set ("Fahrstraße frei") once all of them show green.
 */
function RouteSignals({ account }: { account: EbayStatusOut }) {
  const open = new Set(account.blockers);
  const ready = isReady(account);
  return (
    <div className="mt-6 rounded-sm bg-sunken px-4 py-4">
      <p className="flex items-center gap-2 label-caps text-ink-tertiary">
        Fahrstraße
        <span className={cn("font-medium normal-case tracking-normal", ready ? "text-success" : "text-warning")}>
          {ready ? "frei: Angebote gehen online" : "noch nicht frei"}
        </span>
      </p>
      <ol className="relative mt-4 grid gap-3 sm:grid-cols-5 sm:gap-2">
        {/* The track the signals stand on. */}
        <span aria-hidden="true" className="absolute top-2 right-4 left-4 hidden h-px bg-line-strong sm:block" />
        {READINESS_STEPS.map((step) => {
          const done = !open.has(step.blocker);
          return (
            <li key={step.blocker} className="relative flex items-center gap-2 sm:flex-col sm:items-start sm:gap-2">
              <span className="relative z-10 rounded-full bg-sunken">
                <SignalLamp color={done ? "green" : "red"} />
              </span>
              <span className={cn("text-hint", done ? "text-ink" : "text-ink-secondary")}>
                {step.label}
                <span className="sr-only">{done ? ": erledigt" : ": offen"}</span>
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function DisconnectButton({ onDone }: { onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const disconnect = useMutation<EbayStatusOut, ApiProblem>({
    mutationFn: () => disconnectEbay(),
    onSuccess: () => {
      setOpen(false);
      onDone();
    },
  });
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button type="button" size="sm" variant="secondary" onClick={() => setOpen(true)}>
        Trennen
      </Button>
      <DialogContent>
        <DialogTitle>Verbindung mit eBay trennen?</DialogTitle>
        <DialogDescription>
          Alle Angebote des Shops werden auf eBay beendet. Was du anbieten wolltest, bleibt gemerkt und geht nach dem
          nächsten Verbinden wieder online.
        </DialogDescription>
        {disconnect.isError ? (
          <p role="alert" className="mt-4 text-small text-danger">
            {errorMessage(disconnect.error)}
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
            variant="danger"
            size="sm"
            disabled={disconnect.isPending}
            aria-busy={disconnect.isPending || undefined}
            onClick={() => disconnect.mutate()}
          >
            {disconnect.isPending ? "Wird getrennt …" : "Trennen"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// --- Settings -------------------------------------------------------------------------

function SettingsPanel({ account }: { account: EbayStatusOut }) {
  const owner = useIsOwner();
  const connected = account.status === "connected";
  const policies = useEbayPolicies(connected && owner);
  return (
    <Panel title="Einstellungen" code="EBY 02">
      {!connected ? (
        <p className="text-small text-ink-secondary">
          Nach dem Verbinden wählst du hier Versand, Zahlung und Rücknahme.
        </p>
      ) : policies.isPending && owner ? (
        <PendingNotice>Optionen werden bei eBay abgefragt …</PendingNotice>
      ) : (
        <SettingsForm
          // A fresh form once the saved values change (e.g. after connecting again).
          key={`${account.fulfillment_policy_id}|${account.payment_policy_id}|${account.return_policy_id}|${account.price_markup_percent}|${account.made_to_order_quantity}`}
          account={account}
          policies={policies.data ?? null}
          policiesError={policies.error}
          editable={owner}
        />
      )}
    </Panel>
  );
}

function SettingsForm({
  account,
  policies,
  policiesError,
  editable,
}: {
  account: EbayStatusOut;
  policies: PoliciesOut | null;
  policiesError: ApiProblem | null;
  editable: boolean;
}) {
  const refresh = useEbayRefresh();
  const [fulfillment, setFulfillment] = useState(account.fulfillment_policy_id);
  const [payment, setPayment] = useState(account.payment_policy_id);
  const [returns, setReturns] = useState(account.return_policy_id);
  const [markup, setMarkup] = useState(String(account.price_markup_percent));
  const [quantity, setQuantity] = useState(String(account.made_to_order_quantity));
  const save = useMutation<EbayStatusOut, ApiProblem>({
    mutationFn: () =>
      changeEbaySettings({
        fulfillment_policy_id: fulfillment,
        payment_policy_id: payment,
        return_policy_id: returns,
        price_markup_percent: Number(markup),
        made_to_order_quantity: Number(quantity),
      }),
    onSuccess: refresh,
  });
  const markupValue = Number.isFinite(Number(markup)) ? Math.max(0, Math.min(100, Number(markup))) : 0;

  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate();
  }

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      {policiesError ? (
        <p role="alert" className="text-small text-danger">
          {errorMessage(policiesError)}
        </p>
      ) : null}
      <PolicySelect
        label="Versand"
        value={fulfillment}
        onChange={setFulfillment}
        options={policies?.fulfillment}
        disabled={!editable}
      />
      <PolicySelect
        label="Zahlung"
        value={payment}
        onChange={setPayment}
        options={policies?.payment}
        disabled={!editable}
      />
      <PolicySelect
        label="Rücknahme"
        value={returns}
        onChange={setReturns}
        options={policies?.returns}
        disabled={!editable}
      />
      <div className="grid grid-cols-2 gap-4">
        <FormField
          label="Aufschlag (%)"
          hint={`${formatPrice(EXAMPLE_PRICE_CENTS)} → ${formatPrice(priceWithMarkup(EXAMPLE_PRICE_CENTS, markupValue))}`}
        >
          {(control) => (
            <Input
              {...control}
              type="number"
              inputMode="numeric"
              min={0}
              max={100}
              value={markup}
              disabled={!editable}
              onChange={(event) => setMarkup(event.target.value)}
            />
          )}
        </FormField>
        <FormField label="Auf Bestellung" hint="Stück je Ausführung auf eBay">
          {(control) => (
            <Input
              {...control}
              type="number"
              inputMode="numeric"
              min={1}
              max={20}
              value={quantity}
              disabled={!editable}
              onChange={(event) => setQuantity(event.target.value)}
            />
          )}
        </FormField>
      </div>
      <p className="text-hint text-ink-tertiary">
        Der Aufschlag deckt eBays Gebühren. Modelle auf Bestellung bietet eBay mit dieser Stückzahl an, auch ohne
        Bestand; jeder Verkauf wird gefertigt.
      </p>
      {save.isError ? (
        <p role="alert" className="text-small text-danger">
          {errorMessage(save.error)}
        </p>
      ) : null}
      {editable ? (
        <div className="flex items-center gap-3">
          <Button type="submit" size="sm" disabled={save.isPending} aria-busy={save.isPending || undefined}>
            {save.isPending ? "Wird gespeichert …" : "Speichern"}
          </Button>
          {save.isSuccess ? (
            <span className="text-hint text-success">Gespeichert. Alle Angebote werden angepasst.</span>
          ) : null}
        </div>
      ) : null}
    </form>
  );
}

function PolicySelect({
  label,
  value,
  onChange,
  options,
  disabled,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: readonly PolicyOptionOut[] | undefined;
  disabled: boolean;
}) {
  const known = options ?? [];
  const missing = value !== "" && !known.some((option) => option.id === value);
  return (
    <FormField
      label={label}
      hint={known.length === 0 && !disabled ? "Lege die Option auf eBay unter „Grundsätze“ an." : undefined}
    >
      {(control) => (
        <Select {...control} value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
          <option value="">Bitte wählen</option>
          {known.map((option) => (
            <option key={option.id} value={option.id}>
              {option.name}
            </option>
          ))}
          {missing ? <option value={value}>{`Gewählt: ${value}`}</option> : null}
        </Select>
      )}
    </FormField>
  );
}

// --- Categories -----------------------------------------------------------------------

function CategoriesPanel() {
  const owner = useIsOwner();
  const categories = useEbayCategories(true);
  return (
    <Panel title="Kategorien" code="EBY 03">
      <p className="mb-4 text-hint text-ink-tertiary">
        Jede Shop-Kategorie bekommt die Nummer einer eBay-Kategorie, z. B. 180250 für Modellbau-LKW. Die Nummer steht
        auf eBay in der Adresse der Kategorie. Unterkategorien ohne eigene Nummer nehmen die ihrer Oberkategorie.
      </p>
      {categories.isPending ? (
        <PendingNotice>Kategorien werden geladen …</PendingNotice>
      ) : categories.isError ? (
        <p role="alert" className="text-small text-danger">
          {errorMessage(categories.error)}
        </p>
      ) : categories.data.length === 0 ? (
        <p className="text-small text-ink-secondary">Der Katalog hat noch keine Kategorien.</p>
      ) : (
        <CategoryForm key={categories.dataUpdatedAt} mappings={categories.data} editable={owner} />
      )}
    </Panel>
  );
}

function CategoryForm({ mappings, editable }: { mappings: readonly CategoryMappingOut[]; editable: boolean }) {
  const refresh = useEbayRefresh();
  const [numbers, setNumbers] = useState<Record<string, string>>(() =>
    Object.fromEntries(mappings.map((mapping) => [mapping.category_id, mapping.ebay_category_id])),
  );
  const save = useMutation<unknown, ApiProblem>({
    mutationFn: () =>
      setEbayCategories({
        items: Object.entries(numbers).map(([category_id, ebay_category_id]) => ({
          category_id,
          ebay_category_id: ebay_category_id.trim(),
        })),
      }),
    onSuccess: refresh,
  });

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        save.mutate();
      }}
      noValidate
    >
      <ul className="divide-y divide-line">
        {mappings.map((mapping) => {
          const depth = mapping.path.split(" / ").length - 1;
          const name = mapping.path.split(" / ").at(-1) ?? mapping.path;
          return (
            <li key={mapping.category_id} className="flex items-center justify-between gap-4 py-2">
              <label
                htmlFor={`ebay-category-${mapping.category_id}`}
                className="min-w-0 text-small"
                style={{ paddingLeft: `${depth * 1.25}rem` }}
                title={mapping.path}
              >
                {depth > 0 ? (
                  <span aria-hidden="true" className="mr-2 text-ink-tertiary">
                    └
                  </span>
                ) : null}
                {name}
              </label>
              <Input
                id={`ebay-category-${mapping.category_id}`}
                className="w-32 shrink-0 font-mono tabular-nums"
                inputMode="numeric"
                maxLength={10}
                placeholder="keine"
                value={numbers[mapping.category_id] ?? ""}
                disabled={!editable}
                onChange={(event) =>
                  setNumbers((current) => ({
                    ...current,
                    [mapping.category_id]: event.target.value.replace(/\D/g, ""),
                  }))
                }
              />
            </li>
          );
        })}
      </ul>
      {save.isError ? (
        <p role="alert" className="mt-3 text-small text-danger">
          {errorMessage(save.error)}
        </p>
      ) : null}
      {editable ? (
        <div className="mt-4 flex items-center gap-3">
          <Button type="submit" size="sm" disabled={save.isPending} aria-busy={save.isPending || undefined}>
            {save.isPending ? "Wird gespeichert …" : "Kategorien speichern"}
          </Button>
          {save.isSuccess ? <span className="text-hint text-success">Gespeichert.</span> : null}
        </div>
      ) : null}
    </form>
  );
}
