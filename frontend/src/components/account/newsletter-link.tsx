"use client";

import { useState } from "react";

import { ResultPanel } from "@/components/forms/result-panel";
import { Button } from "@/components/ui/button";
import { TextLink } from "@/components/ui/text-link";
import {
  useConfirmNewsletter,
  useUnsubscribeNewsletter,
} from "@/lib/api/generated/store-newsletter/store-newsletter";
import { errorMessage } from "@/lib/i18n/problems";

type Action = "confirm" | "unsubscribe";

const TEXT = {
  confirm: {
    explanation: "Ein Klick noch, dann bekommst du einmal im Monat die neuen Modelle aus der Werkstatt.",
    button: "Newsletter bestätigen",
    pending: "Wird bestätigt …",
    doneTitle: "Du bist dabei",
    done: "Ab jetzt erfährst du als Erste:r, was neu vom Drucker kommt, und was zu deiner Sammlung passt.",
  },
  unsubscribe: {
    explanation: "Nach dem Klick schicken wir dir keinen Newsletter mehr. Dein Kundenkonto bleibt, wie es ist.",
    button: "Newsletter abbestellen",
    pending: "Wird abbestellt …",
    doneTitle: "Abbestellt",
    done: "Du bekommst keinen Newsletter mehr. Im Kundenkonto kannst du ihn jederzeit wieder bestellen.",
  },
} as const satisfies Record<Action, Record<string, string>>;

/**
 * The page behind the link in a newsletter mail. It acts only on a click: mail scanners
 * that open links on their own must not confirm or end the newsletter.
 */
export function NewsletterLink({ action, token }: { action: Action; token: string | null }) {
  const confirm = useConfirmNewsletter();
  const unsubscribe = useUnsubscribeNewsletter();
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
          <TextLink href="/katalog">Zu den Modellen</TextLink>
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
