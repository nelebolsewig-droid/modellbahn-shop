"use client";

import { PasswordChangeForm } from "@/components/forms/password-change-form";
import { Badge } from "@/components/ui/badge";
import type { AccountOut } from "@/lib/api/generated/model";
import { useChangeCustomerPassword } from "@/lib/api/generated/store-account/store-account";
import { formatLongDate } from "@/lib/format";

import { CustomerGate } from "./customer-gate";
import { DeleteAccount } from "./delete-account";
import { DisplayNameForm } from "./display-name-form";
import { LogoutButton } from "./logout-button";
import { SettingsSection } from "./settings-section";

/** "Mein Konto": the customer's data and settings, as far as the API confirms a session. */
export function AccountOverview() {
  return (
    <CustomerGate pending="Dein Konto wird geladen …">
      {({ account, leave }) => (
        <AccountDetails account={account} onLoggedOut={() => leave("/")} onDeleted={() => leave("/konto/geloescht")} />
      )}
    </CustomerGate>
  );
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
