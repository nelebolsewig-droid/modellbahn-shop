"use client";

import { useCallback, useEffect, useEffectEvent, useRef, useState } from "react";

/**
 * - connecting: a connection is being opened
 * - open: connected, events arrive live
 * - reconnecting: connection lost; the browser retries on its own and sends
 *   Last-Event-ID, so the API replays what was missed
 * - closed: the browser gave up (the API answered with an error, e.g. 401 or a 502
 *   from the proxy while the API restarts); a new EventSource is opened after a pause.
 *   A new EventSource cannot send Last-Event-ID, so it asks for the replay with the
 *   `last_event_id` query parameter instead.
 */
export type StreamState = "connecting" | "open" | "reconnecting" | "closed";

/** Pause before a new connection once the browser has given up. */
export const RETRY_AFTER_CLOSE_MS = 15_000;

/** The stream URL that resumes after `lastEventId` (the API replays what came later). */
export function resumeUrl(url: string, lastEventId: string | null): string {
  if (lastEventId === null) {
    return url;
  }
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}last_event_id=${encodeURIComponent(lastEventId)}`;
}

type EventStreamOptions = {
  url: string;
  /** Named SSE events to listen for (the `event:` field of each message). */
  eventTypes: readonly string[];
  onMessage: (data: string) => void;
  /** Called when the browser has given up on the connection. */
  onClosed?: () => void;
};

/** Subscribes to a Server-Sent Events stream with the browser's EventSource. */
export function useEventStream({ url, eventTypes, onMessage, onClosed }: EventStreamOptions) {
  const [state, setState] = useState<StreamState>("connecting");
  const [attempt, setAttempt] = useState(0);
  const handleMessage = useEffectEvent((event: MessageEvent<string>) => onMessage(event.data));
  const handleClosed = useEffectEvent(() => onClosed?.());
  const typesKey = eventTypes.join("\n");
  // The id of the last event received from `url`; it survives a new EventSource.
  const cursor = useRef<{ url: string; id: string } | null>(null);

  const reconnect = useCallback(() => {
    setState("connecting");
    setAttempt((current) => current + 1);
  }, []);

  useEffect(() => {
    // Same origin, so the session cookie is sent without withCredentials.
    const lastEventId = cursor.current?.url === url ? cursor.current.id : null;
    const source = new EventSource(resumeUrl(url, lastEventId));
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    const listener = (event: MessageEvent<string>) => {
      if (event.lastEventId) {
        cursor.current = { url, id: event.lastEventId };
      }
      handleMessage(event);
    };

    source.addEventListener("open", () => setState("open"));
    source.addEventListener("error", () => {
      if (source.readyState === EventSource.CLOSED) {
        setState("closed");
        handleClosed();
        retryTimer = setTimeout(reconnect, RETRY_AFTER_CLOSE_MS);
      } else {
        setState("reconnecting");
      }
    });
    for (const type of typesKey.split("\n").filter(Boolean)) {
      source.addEventListener(type, listener);
    }

    return () => {
      clearTimeout(retryTimer);
      source.close();
    };
  }, [url, typesKey, attempt, reconnect]);

  return { state, reconnect };
}
