"use client";

import { useState } from "react";

import { formatEventTime } from "@/lib/format";
import {
  ADMIN_EVENTS_URL,
  mergeFeed,
  parseFeedEntry,
  STAFF_EVENT_TYPES,
  type FeedEntry,
} from "@/lib/realtime/events";
import { useEventStream } from "@/lib/realtime/use-event-stream";

import { ConnectionLamp } from "./connection-lamp";
import { Panel } from "./panel";

/** The feed keeps the newest entries of this visit; older ones scroll away. */
const FEED_LIMIT = 50;

function announcement(entry: FeedEntry): string {
  return entry.account ? `${entry.label}: ${entry.account.displayName}` : entry.label;
}

/**
 * Live events for the staff (registrations, verified e-mail addresses), pushed by the
 * API as Server-Sent Events. Starts empty: it shows what happens while it is open,
 * plus whatever the browser's automatic reconnect replays.
 */
export function EventFeed({ onStreamClosed }: { onStreamClosed: () => void }) {
  const [entries, setEntries] = useState<FeedEntry[]>([]);
  const [latest, setLatest] = useState("");
  const { state, reconnect } = useEventStream({
    url: ADMIN_EVENTS_URL,
    eventTypes: STAFF_EVENT_TYPES,
    onMessage(data) {
      const entry = parseFeedEntry(data);
      if (entry === null) {
        return;
      }
      setEntries((current) => mergeFeed(current, entry, FEED_LIMIT));
      setLatest(announcement(entry));
    },
    onClosed: onStreamClosed,
  });

  return (
    <Panel
      title="Ereignisse"
      code="STW 01"
      actions={<ConnectionLamp state={state} onReconnect={reconnect} />}
      className="min-h-80"
    >
      {/* Announces each new entry once; the list itself is not a live region. */}
      <p className="sr-only" aria-live="polite">
        {latest}
      </p>
      {entries.length === 0 ? (
        <EmptyFeed />
      ) : (
        <ol aria-label="Neueste Ereignisse zuerst" className="relative">
          {entries.map((entry, index) => (
            <FeedItem key={entry.id} entry={entry} isNewest={index === 0} />
          ))}
        </ol>
      )}
    </Panel>
  );
}

function FeedItem({ entry, isNewest }: { entry: FeedEntry; isNewest: boolean }) {
  return (
    <li className="group relative grid grid-cols-[1.25rem_minmax(0,1fr)] gap-x-4 pb-6 last:pb-0">
      {/* The track: a rail running down the list, a node per event. */}
      <span aria-hidden="true" className="relative flex justify-center">
        <span className="absolute top-0 bottom-0 w-[1.5px] bg-line-strong group-first:top-2 group-last:bottom-auto group-last:h-2" />
        <span
          className={
            isNewest
              ? "relative mt-1 size-3 rounded-full bg-accent shadow-[0_0_10px_1px_var(--color-accent)]"
              : "relative mt-1 size-3 rounded-full bg-surface-raised ring-[1.5px] ring-line-strong"
          }
        />
      </span>
      <div className={isNewest ? "animate-feed-in" : undefined}>
        <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="font-medium">{entry.label}</span>
          <time dateTime={entry.occurredAt.toISOString()} className="font-mono text-sm text-ink-muted">
            {formatEventTime(entry.occurredAt)}
          </time>
        </p>
        {entry.account ? <p className="mt-1 break-words">{entry.account.displayName}</p> : null}
        <p className="mt-1 font-mono text-xs break-all text-ink-muted">
          {entry.type}
          {entry.truncated ? " · gekürzt" : null}
        </p>
      </div>
    </li>
  );
}

function EmptyFeed() {
  return (
    <div className="rule rounded-sm border-dashed border-line px-5 py-10 text-center">
      <p className="label-caps text-ink-muted">Gleis frei</p>
      <p className="mx-auto mt-3 max-w-sm text-sm leading-6 text-ink-muted">
        Seit dem Öffnen dieser Seite ist nichts passiert. Neue Registrierungen und bestätigte
        E-Mail-Adressen erscheinen hier sofort, ohne Neuladen.
      </p>
    </div>
  );
}
