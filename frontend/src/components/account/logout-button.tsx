"use client";

import { Button } from "@/components/ui/button";
import { useLogoutCustomer } from "@/lib/api/generated/store-account/store-account";
import { errorMessage } from "@/lib/i18n/problems";

export function LogoutButton({ onLoggedOut }: { onLoggedOut: () => void }) {
  const logout = useLogoutCustomer();
  return (
    <div>
      <Button
        type="button"
        variant="secondary"
        disabled={logout.isPending}
        aria-busy={logout.isPending || undefined}
        onClick={() => logout.mutate(undefined, { onSuccess: onLoggedOut })}
      >
        {logout.isPending ? "Abmelden …" : "Abmelden"}
      </Button>
      <p role="alert" className="text-small font-medium text-danger not-empty:mt-2">
        {logout.isError ? errorMessage(logout.error) : null}
      </p>
    </div>
  );
}
