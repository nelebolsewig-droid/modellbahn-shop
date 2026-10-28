"use client";

import { useState, useSyncExternalStore } from "react";

import { Button } from "@/components/ui/button";
import { FAIR_FEED_PATH, webcalUrl } from "@/lib/site/fairs";

const noSubscription = () => () => {};

/** The site's own origin; empty while rendering on the server. */
function useOrigin(): string {
  return useSyncExternalStore(
    noSubscription,
    () => window.location.origin,
    () => "",
  );
}

/**
 * All fairs as a calendar subscription: new dates appear in the visitor's calendar by
 * themselves. Apple and Outlook open webcal:// links; Google Calendar wants the
 * address pasted ("Per URL hinzufügen"), hence the copy button.
 */
export function CalendarSubscription() {
  const origin = useOrigin();
  const [copied, setCopied] = useState(false);
  const feedUrl = `${origin}${FAIR_FEED_PATH}`;

  return (
    <div className="flex flex-wrap gap-2">
      <Button asChild size="sm">
        {/* Before hydration the plain path still downloads the calendar. */}
        <a href={origin ? webcalUrl(origin) : FAIR_FEED_PATH}>Kalender abonnieren</a>
      </Button>
      <Button
        type="button"
        variant="secondary"
        size="sm"
        disabled={!origin}
        onClick={() => {
          void navigator.clipboard.writeText(feedUrl).then(() => setCopied(true));
        }}
      >
        {copied ? "Adresse kopiert" : "Adresse kopieren"}
      </Button>
      <span role="status" className="sr-only">
        {copied ? "Die Adresse des Kalenders ist in der Zwischenablage." : ""}
      </span>
    </div>
  );
}
