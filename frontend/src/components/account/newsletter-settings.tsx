"use client";

import { useQueryClient } from "@tanstack/react-query";

import { ResultPanel } from "@/components/forms/result-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  getGetNewsletterQueryKey,
  useGetNewsletter,
  useSetNewsletter,
} from "@/lib/api/generated/store-newsletter/store-newsletter";
import { errorMessage } from "@/lib/i18n/problems";

/**
 * The newsletter switch on "Mein Konto". Switching it on mails a confirmation link
 * (double opt-in); switching it off ends the newsletter at once.
 */
export function NewsletterSettings({ emailVerified }: { emailVerified: boolean }) {
  const queryClient = useQueryClient();
  const status = useGetNewsletter();
  const change = useSetNewsletter({
    mutation: {
      onSuccess: (data) => queryClient.setQueryData(getGetNewsletterQueryKey(), data),
    },
  });
  const current = status.data?.status;

  if (status.isPending) {
    return <p className="text-small text-ink-secondary">Wird geladen …</p>;
  }
  if (status.isError) {
    return (
      <ResultPanel tone="danger" title="Das hat nicht geklappt">
        <p>{errorMessage(status.error)}</p>
      </ResultPanel>
    );
  }
  return (
    <div className="space-y-4">
      <p>
        {current === "confirmed" ? (
          <Badge tone="success">Bestellt</Badge>
        ) : current === "pending" ? (
          <Badge tone="warning">Wartet auf deine Bestätigung</Badge>
        ) : (
          <Badge>Nicht bestellt</Badge>
        )}
      </p>
      {current === "pending" ? (
        <p className="text-small text-ink-secondary">
          {emailVerified
            ? "Wir haben dir einen Link geschickt. Erst nach dem Klick darauf bekommst du den Newsletter."
            : "Bestätige zuerst deine E-Mail-Adresse; danach schicken wir dir den Link für den Newsletter."}
        </p>
      ) : null}
      {change.isError ? (
        <ResultPanel tone="danger" title="Das hat nicht geklappt">
          <p>{errorMessage(change.error)}</p>
        </ResultPanel>
      ) : null}
      <div className="flex flex-wrap gap-3">
        {current === "none" ? (
          <Button
            type="button"
            disabled={change.isPending}
            aria-busy={change.isPending || undefined}
            onClick={() => change.mutate({ data: { subscribed: true } })}
          >
            Newsletter bestellen
          </Button>
        ) : (
          <>
            {current === "pending" && emailVerified ? (
              <Button
                type="button"
                variant="secondary"
                disabled={change.isPending}
                onClick={() => change.mutate({ data: { subscribed: true } })}
              >
                Link erneut schicken
              </Button>
            ) : null}
            <Button
              type="button"
              variant="secondary"
              disabled={change.isPending}
              aria-busy={change.isPending || undefined}
              onClick={() => change.mutate({ data: { subscribed: false } })}
            >
              Newsletter abbestellen
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
