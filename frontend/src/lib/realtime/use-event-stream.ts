"use client";

import { useEffect, useEffectEvent, useState } from "react";

/**
 * - connecting: first connection is being opened
 * - open: connected, events arrive live
 * - reconnecting: connection lost; the browser retries on its own and sends
 *   Last-Event-ID, so the API replays what was missed
 * - closed: the browser gave up (e.g. the API answered 401); only a new
 *   EventSource helps
 */
export type StreamState = "connecting" | "open" | "reconnecting" | "closed";

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

  useEffect(() => {
    // Same origin, so the session cookie is sent without withCredentials.
    const source = new EventSource(url);
    const types = typesKey.split("\n").filter(Boolean);

    source.addEventListener("open", () => setState("open"));
    source.addEventListener("error", () => {
      if (source.readyState === EventSource.CLOSED) {
        setState("closed");
        handleClosed();
      } else {
        setState("reconnecting");
      }
    });
    for (const type of types) {
      source.addEventListener(type, handleMessage);
    }
    return () => source.close();
  }, [url, typesKey, attempt]);

  /** Opens a new connection after the browser has given up. */
  function reconnect() {
    setState("connecting");
    setAttempt((current) => current + 1);
  }

  return { state, reconnect };
}
