"use client";

import { useState } from "react";

import { ResultPanel } from "@/components/forms/result-panel";
import { Button } from "@/components/ui/button";
import { TextLink } from "@/components/ui/text-link";
import { useConfirmFairNews, useUnsubscribeFairNews } from "@/lib/api/generated/store-site/store-site";
import { errorMessage } from "@/lib/i18n/problems";

type Action = "confirm" | "unsubscribe";

const TEXT = {
  confirm: {
    explanation: "Ein Klick noch, dann bekommst du eine E-Mail, sobald wir eine neue Messe ankündigen.",
    button: "Messe-Post bestätigen",
    pending: "Wird bestätigt …",
    doneTitle: "Du bist dabei",
    done: "Ab jetzt sagen wir dir Bescheid, wenn wir auf einer Messe ausstellen. Bis bald am Stand!",
  },
  unsubscribe: {
    explanation: "Nach dem Klick schicken wir dir keine Messe-Post mehr und löschen deine Adresse.",
    button: "Von der Messe-Post abmelden",
    pending: "Wird abgemeldet …",
    doneTitle: "Abgemeldet",
    done: "Deine Adresse ist gelöscht; du bekommst keine Messe-Post mehr.",
  },
} as const satisfies Record<Action, Record<string, string>>;

/**
 * The page behind the link in a fair news mail. It acts only on a click: mail
 * scanners that open links on their own must not confirm or end a subscription.
 */
export function FairNewsLink({ action, token }: { action: Action; token: string | null }) {
  const confirm = useConfirmFairNews();
  const unsubscribe = useUnsubscribeFairNews();
  const mutation = action === "confirm" ? confirm : unsubscribe;
  const [done, setDone] = useState(false);
  const text = TEXT[action];

  if (token === null) {
    return (
      <ResultPanel tone="danger" title="Der Link ist unvollständig">
        <p>Bitte öffne den Link direkt aus der E-Mail.</p>
      </ResultPanel>
    );
  }
  if (done) {
    return (
      <ResultPanel tone="success" title={text.doneTitle}>
        <p>{text.done}</p>
        <p className="mt-2">
          <TextLink href="/termine">Zu den Terminen</TextLink>
        </p>
      </ResultPanel>
    );
  }
  return (
    <div className="space-y-5">
      <p className="text-ink-secondary">{text.explanation}</p>
      {mutation.isError ? (
        <ResultPanel tone="danger" title="Das hat nicht geklappt">
          <p>{errorMessage(mutation.error)}</p>
        </ResultPanel>
      ) : null}
      <Button
        type="button"
        className="w-full"
        variant={action === "confirm" ? "primary" : "secondary"}
        disabled={mutation.isPending}
        aria-busy={mutation.isPending || undefined}
        onClick={() => mutation.mutate({ data: { token } }, { onSuccess: () => setDone(true) })}
      >
        {mutation.isPending ? text.pending : text.button}
      </Button>
    </div>
  );
}
