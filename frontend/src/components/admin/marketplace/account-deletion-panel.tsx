"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { Panel } from "@/components/admin/panel";
import { Button } from "@/components/ui/button";
import { PendingNotice } from "@/components/ui/pending-notice";
import { SignalLamp } from "@/components/ui/signal-lamp";
import { closeEbayTestBuyerAccount } from "@/lib/api/generated/admin-marketplace/admin-marketplace";
import type { AccountDeletionSetupOut, TestAccountClosedOut } from "@/lib/api/generated/model";
import type { ApiProblem } from "@/lib/api/problem";
import { errorMessage } from "@/lib/i18n/problems";

import { useAccountDeletionSetup, useEbayRefresh } from "./use-ebay";

/**
 * eBay's notifications of closed accounts (ADR 0015). eBay enables the production keys
 * only once the developer account names this endpoint, so the panel shows the address
 * to enter there, also while eBay is still off. On the test marketplace the test buyer
 * can close their account to show what happens.
 */
export function AccountDeletionPanel() {
  const setup = useAccountDeletionSetup();
  return (
    <Panel title="Löschmeldungen von eBay" code="EBY 07">
      {setup.isPending ? (
        <PendingNotice>Wird geladen …</PendingNotice>
      ) : setup.isError ? (
        <p role="alert" className="text-small text-danger">
          {errorMessage(setup.error)}
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div className="min-w-0 space-y-3 text-small text-ink-secondary">
            <p>
              Schließt jemand sein eBay-Konto, meldet eBay das jedem Entwicklerkonto. Der Shop löscht dann Name, E-Mail
              und Anschrift aus den eBay-Bestellungen dieses Käufers. Die Shop-Bestellung bleibt für die
              Aufbewahrungsfristen erhalten, wie bei einem gelöschten Kundenkonto.
            </p>
            <p>
              Fast alle Meldungen betreffen fremde Leute. Von ihnen speichert der Shop nichts, auch nicht im Protokoll.
            </p>
            <p className="text-hint text-ink-tertiary">
              eBay gibt die Produktions-Schlüssel erst frei, wenn diese Adresse mit dem Prüftoken im Entwicklerkonto
              eingetragen ist (Application Keys → Alerts &amp; Notifications).
            </p>
          </div>
          <SetupDetails setup={setup.data} />
        </div>
      )}
    </Panel>
  );
}

function SetupDetails({ setup }: { setup: AccountDeletionSetupOut }) {
  return (
    <div className="min-w-0 space-y-4">
      <EndpointAddress endpoint={setup.endpoint} />
      <ul className="space-y-2 text-small">
        <li className="flex items-start gap-2">
          <SignalLamp color={setup.token_set ? "green" : "yellow"} className="mt-0.5" />
          <span>
            {setup.token_set ? (
              "Prüftoken gesetzt: eBays Prüfung der Adresse bekommt ihre Antwort."
            ) : (
              <>
                Prüftoken fehlt: <code className="font-mono">MB_EBAY_VERIFICATION_TOKEN</code> auf dem Server setzen.
              </>
            )}
          </span>
        </li>
        <li className="flex items-start gap-2">
          <SignalLamp color={setup.checks_signatures ? "green" : "off"} className="mt-0.5" />
          <span>
            {setup.checks_signatures
              ? "Jede Meldung wird gegen eBays Signatur geprüft."
              : "eBay ist aus: Meldungen werden quittiert, solange keine Bestellung Käuferdaten trägt."}
          </span>
        </li>
      </ul>
      {setup.test_buyer_name ? <TestBuyerCloses buyerName={setup.test_buyer_name} /> : null}
    </div>
  );
}

function EndpointAddress({ endpoint }: { endpoint: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div>
      <p className="text-label uppercase tracking-wider text-ink-tertiary">Adresse für das Entwicklerkonto</p>
      <div className="mt-1.5 flex flex-wrap items-center gap-2">
        <code className="min-w-0 flex-1 rounded-sm border border-line bg-sunken px-2.5 py-1.5 font-mono text-hint break-all">
          {endpoint}
        </code>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={() => {
            void navigator.clipboard.writeText(endpoint).then(() => setCopied(true));
          }}
        >
          {copied ? "Kopiert" : "Kopieren"}
        </Button>
      </div>
      <span role="status" className="sr-only">
        {copied ? "Die Adresse ist in der Zwischenablage." : ""}
      </span>
    </div>
  );
}

function TestBuyerCloses({ buyerName }: { buyerName: string }) {
  const refresh = useEbayRefresh();
  const close = useMutation<TestAccountClosedOut, ApiProblem>({
    mutationFn: () => closeEbayTestBuyerAccount(),
    onSettled: refresh,
  });
  return (
    <div className="border-t border-line pt-4">
      <p className="text-hint text-ink-tertiary">
        Testmarktplatz: Der Testkäufer <span className="font-mono">{buyerName}</span> schließt sein eBay-Konto. Die
        Meldung ist signiert wie eine echte und läuft durch dieselbe Prüfung.
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={close.isPending}
          aria-busy={close.isPending || undefined}
          onClick={() => close.mutate()}
        >
          {close.isPending ? "Meldet …" : "Konto des Testkäufers schließen"}
        </Button>
        <span role="status" className="text-hint">
          {close.isSuccess ? (
            <span className="text-success">
              {close.data.erased_orders === 0
                ? "Gemeldet. Keine Bestellung trug noch seine Daten."
                : close.data.erased_orders === 1
                  ? "Gemeldet. Käuferdaten in 1 Bestellung gelöscht."
                  : `Gemeldet. Käuferdaten in ${close.data.erased_orders} Bestellungen gelöscht.`}
            </span>
          ) : null}
        </span>
      </div>
      {close.isError ? (
        <p role="alert" className="mt-2 text-hint text-danger">
          {errorMessage(close.error)}
        </p>
      ) : null}
    </div>
  );
}
