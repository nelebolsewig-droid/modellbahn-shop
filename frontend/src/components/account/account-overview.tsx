"use client";

import { PasswordChangeForm } from "@/components/forms/password-change-form";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PendingNotice } from "@/components/ui/pending-notice";
import type { AccountOut } from "@/lib/api/generated/model";
import { useChangeCustomerPassword } from "@/lib/api/generated/store-account/store-account";
import { formatLongDate } from "@/lib/format";
import { errorMessage } from "@/lib/i18n/problems";
import { CUSTOMER_AREA } from "@/lib/navigation";
import { useCustomerSession, useCustomerSessionCache } from "@/lib/session/customer";
import { useProtectedArea } from "@/lib/session/use-session-redirects";

import { DeleteAccount } from "./delete-account";
import { DisplayNameForm } from "./display-name-form";
import { LogoutButton } from "./logout-button";
import { SettingsSection } from "./settings-section";

/** "Mein Konto": the customer's data and settings, as far as the API confirms a session. */
export function AccountOverview() {
  const session = useCustomerSession();
  const cache = useCustomerSessionCache();
  const { leave } = useProtectedArea(session, cache, CUSTOMER_AREA);

  switch (session.status) {
    case "loading":
    case "anonymous":
      return <PendingNotice className="mt-10">Dein Konto wird geladen …</PendingNotice>;
    case "error":
      return (
        <div className="mt-10 max-w-xl space-y-4">
          <Alert tone="danger" title="Dein Konto konnte nicht geladen werden">
            <p>{errorMessage(session.error)}</p>
          </Alert>
          <Button type="button" variant="secondary" onClick={() => void cache.revalidate()}>
            Erneut versuchen
          </Button>
        </div>
      );
    case "authenticated":
      return (
        <AccountDetails
          account={session.account}
          onLoggedOut={() => leave("/")}
          onDeleted={() => leave("/konto/geloescht")}
        />
      );
  }
}

type AccountDetailsProps = {
  account: AccountOut;
  onLoggedOut: () => void;
  onDeleted: () => void;
};

function AccountDetails({ account, onLoggedOut, onDeleted }: AccountDetailsProps) {
  const changePassword = useChangeCustomerPassword();

  return (
    <div className="mt-12 grid items-start gap-6 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)] lg:gap-8">
      <section
        aria-labelledby="profil"
        className="rounded-lg bg-surface p-6 sm:p-8 lg:sticky lg:top-8"
      >
        <h2 id="profil" className="text-heading break-words">
          Hallo, {account.display_name}
        </h2>
        <dl className="mt-6 space-y-5">
          <div>
            <dt className="label-caps text-ink-tertiary">E-Mail-Adresse</dt>
            <dd className="mt-1 break-all">{account.email}</dd>
            <dd className="mt-2">
              {account.email_verified ? (
                <Badge tone="success">Bestätigt</Badge>
              ) : (
                <Badge tone="warning">Nicht bestätigt</Badge>
              )}
            </dd>
          </div>
          <div>
            <dt className="label-caps text-ink-tertiary">Konto angelegt am</dt>
            <dd className="mt-1">
              <time dateTime={account.created_at}>{formatLongDate(new Date(account.created_at))}</time>
            </dd>
          </div>
        </dl>
        <div className="mt-8">
          <LogoutButton onLoggedOut={onLoggedOut} />
        </div>
      </section>

      <div className="space-y-6">
        <SettingsSection title="Anzeigename" description="So sprechen wir dich an, zum Beispiel in E-Mails.">
          <DisplayNameForm displayName={account.display_name} />
        </SettingsSection>

        <SettingsSection
          title="Passwort ändern"
          description="Nach der Änderung bleibst du hier angemeldet; auf allen anderen Geräten wirst du abgemeldet."
        >
          <PasswordChangeForm
            submit={async (values) => {
              await changePassword.mutateAsync({ data: values });
            }}
          />
        </SettingsSection>

        <SettingsSection
          tone="danger"
          title="Konto löschen"
          description="Wir entfernen deinen Namen, deine E-Mail-Adresse und dein Passwort und melden dich auf allen Geräten ab. Das lässt sich nicht rückgängig machen."
        >
          <DeleteAccount onDeleted={onDeleted} />
        </SettingsSection>
      </div>
    </div>
  );
}
