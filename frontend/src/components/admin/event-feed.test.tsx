import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RETRY_AFTER_CLOSE_MS } from "@/lib/realtime/use-event-stream";
import { FakeEventSource, latestSource } from "@/test/event-source";

import { EventFeed } from "./event-feed";

const REGISTERED = {
  id: "0192f1c4-7a3e-7cc2-9d5e-1b2c3d4e5f60",
  type: "identity.customer.registered",
  occurred_at: "2026-10-22T12:32:05Z",
  data: { account_id: "0192f1c4-0000-7000-8000-000000000001", display_name: "Erika Mustermann" },
  truncated: false,
};

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("EventFeed", () => {
  it("connects to the admin stream and shows the lamp's state in words", () => {
    render(<EventFeed onStreamClosed={vi.fn()} />);
    expect(latestSource().url).toBe("/api/v1/admin/events");
    expect(screen.getByText("Verbindet …")).toBeInTheDocument();

    act(() => latestSource().open());
    expect(screen.getByText("Live verbunden")).toBeInTheDocument();
    expect(screen.getByText(/Seit dem Öffnen dieser Seite ist nichts passiert/)).toBeInTheDocument();
  });

  it("shows a registration live, newest first, and announces it", () => {
    render(<EventFeed onStreamClosed={vi.fn()} />);
    act(() => {
      latestSource().open();
      latestSource().emit("identity.customer.registered", REGISTERED);
      latestSource().emit("identity.account.email_verified", {
        ...REGISTERED,
        id: "0192f1c4-7a3e-7cc2-9d5e-1b2c3d4e5f61",
        type: "identity.account.email_verified",
      });
    });

    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("E-Mail-Adresse bestätigt");
    expect(items[1]).toHaveTextContent("Neue Registrierung");
    expect(items[1]).toHaveTextContent("Erika Mustermann");
    expect(screen.getByText("E-Mail-Adresse bestätigt: Erika Mustermann")).toHaveAttribute(
      "aria-live",
      "polite",
    );
  });

  it("does not show an event twice when the reconnect replays it", () => {
    render(<EventFeed onStreamClosed={vi.fn()} />);
    act(() => {
      latestSource().emit("identity.customer.registered", REGISTERED);
      latestSource().fail({ closed: false });
    });
    expect(screen.getByText("Unterbrochen – verbindet neu …")).toBeInTheDocument();

    act(() => {
      latestSource().open();
      latestSource().emit("identity.customer.registered", REGISTERED);
    });
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
  });

  it("turns red when the browser gives up, reports it, and opens a new connection later", () => {
    vi.useFakeTimers();
    const onStreamClosed = vi.fn();
    render(<EventFeed onStreamClosed={onStreamClosed} />);
    act(() => latestSource().fail({ closed: true }));

    expect(screen.getByText("Keine Verbindung")).toBeInTheDocument();
    expect(onStreamClosed).toHaveBeenCalledTimes(1);
    expect(FakeEventSource.instances).toHaveLength(1);

    act(() => vi.advanceTimersByTime(RETRY_AFTER_CLOSE_MS));
    expect(FakeEventSource.instances).toHaveLength(2);
    expect(FakeEventSource.instances[0]?.readyState).toBe(FakeEventSource.CLOSED);
    expect(screen.getByText("Verbindet …")).toBeInTheDocument();
  });

  it("reconnects at once on request", async () => {
    const user = userEvent.setup();
    render(<EventFeed onStreamClosed={vi.fn()} />);
    act(() => latestSource().fail({ closed: true }));

    await user.click(screen.getByRole("button", { name: "Neu verbinden" }));
    expect(FakeEventSource.instances).toHaveLength(2);
    act(() => latestSource().open());
    expect(screen.getByText("Live verbunden")).toBeInTheDocument();
  });

  it("closes the connection when the page is left", () => {
    const { unmount } = render(<EventFeed onStreamClosed={vi.fn()} />);
    const source = latestSource();
    unmount();
    expect(source.readyState).toBe(FakeEventSource.CLOSED);
  });
});
