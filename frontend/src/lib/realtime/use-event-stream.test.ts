import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RETRY_AFTER_CLOSE_MS, resumeUrl, useEventStream } from "./use-event-stream";

/** Just enough of EventSource for the hook: listeners, readyState, close(). */
class FakeEventSource extends EventTarget {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 2;
  static opened: FakeEventSource[] = [];

  readyState = FakeEventSource.CONNECTING;

  constructor(readonly url: string) {
    super();
    FakeEventSource.opened.push(this);
  }

  close() {
    this.readyState = FakeEventSource.CLOSED;
  }

  emit(type: string, data: string, lastEventId: string) {
    this.dispatchEvent(new MessageEvent(type, { data, lastEventId }));
  }

  giveUp() {
    this.readyState = FakeEventSource.CLOSED;
    this.dispatchEvent(new Event("error"));
  }
}

const STREAM_URL = "/api/v1/admin/events";

beforeEach(() => {
  FakeEventSource.opened = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

function latest(): FakeEventSource {
  const source = FakeEventSource.opened.at(-1);
  if (source === undefined) {
    throw new Error("no EventSource was opened");
  }
  return source;
}

describe("resumeUrl", () => {
  it("adds the cursor as a query parameter", () => {
    expect(resumeUrl(STREAM_URL, null)).toBe(STREAM_URL);
    expect(resumeUrl(STREAM_URL, "0199a8c0-0000-7000-8000-00000000000a")).toBe(
      `${STREAM_URL}?last_event_id=0199a8c0-0000-7000-8000-00000000000a`,
    );
    expect(resumeUrl(`${STREAM_URL}?x=1`, "a b")).toBe(`${STREAM_URL}?x=1&last_event_id=a%20b`);
  });
});

describe("useEventStream", () => {
  it("resumes after the last event when it has to open a new connection", () => {
    const onMessage = vi.fn();
    renderHook(() => useEventStream({ url: STREAM_URL, eventTypes: ["identity.x"], onMessage }));
    expect(latest().url).toBe(STREAM_URL);

    act(() => latest().emit("identity.x", "{}", "event-7"));
    act(() => latest().giveUp());
    act(() => vi.advanceTimersByTime(RETRY_AFTER_CLOSE_MS));

    expect(onMessage).toHaveBeenCalledWith("{}");
    expect(FakeEventSource.opened).toHaveLength(2);
    expect(latest().url).toBe(`${STREAM_URL}?last_event_id=event-7`);
  });

  it("resumes on a manual reconnect, too", () => {
    const { result } = renderHook(() =>
      useEventStream({ url: STREAM_URL, eventTypes: ["identity.x"], onMessage: vi.fn() }),
    );
    act(() => latest().emit("identity.x", "{}", "event-9"));

    act(() => result.current.reconnect());

    expect(latest().url).toBe(`${STREAM_URL}?last_event_id=event-9`);
  });
});
