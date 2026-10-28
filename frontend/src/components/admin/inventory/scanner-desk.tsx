"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { Route } from "next";
import Link from "next/link";
import { useCallback, useEffect, useEffectEvent, useRef, useState, type FormEvent } from "react";

import { ConnectionLamp } from "@/components/admin/connection-lamp";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { OptionGroup, OptionPill } from "@/components/ui/option-pill";
import { Select } from "@/components/ui/select";
import { StatusBadge } from "@/components/ui/status-badge";
import {
  allocateOrder,
  getGetPickListQueryKey,
  getListStockQueryKey,
  recordScan,
  undoScan,
  useGetPickList,
} from "@/lib/api/generated/admin-inventory/admin-inventory";
import { getListOrdersQueryKey, listOrders } from "@/lib/api/generated/admin-sales/admin-sales";
import { ScanMode, type ScanIn, type ScanOut, type StaffRole } from "@/lib/api/generated/model";
import { interpretations } from "@/lib/inventory/codes";
import { signal, unlockSound } from "@/lib/inventory/feedback";
import { scanFeedback, SCAN_MODE_LABELS } from "@/lib/inventory/labels";
import { browserScanStore, flushQueue, isUnreachable, type ScanStore } from "@/lib/inventory/scan-queue";
import {
  contextFor,
  initialSession,
  latestAnswer,
  scanSession,
  type ScanEntry,
  type ScanEvent,
  type ScanSource,
} from "@/lib/inventory/scan-session";
import { LabelPicker, RepeatFilter, WedgeReader } from "@/lib/inventory/scanner-input";
import { errorMessage } from "@/lib/i18n/problems";
import { ADMIN_EVENTS_URL, INVENTORY_EVENT_TYPES, ORDER_EVENT_TYPES, orderEventOf, stockEventOf } from "@/lib/realtime/events";
import { useEventStream } from "@/lib/realtime/use-event-stream";
import { cn } from "@/lib/utils";

import { CameraView, type FlashTone } from "./camera-view";
import { PickList, PickProgress } from "./pick-list";
import { entrySummary, ScanResult, scanTime } from "./scan-result";

/** Owner and staff may hand out stock to an order; packers pick what was handed out. */
const MAY_ALLOCATE: ReadonlySet<StaffRole> = new Set(["owner", "staff"]);

/** How often waiting scans try again while the network is gone. */
const RETRY_MS = 20_000;

const MODES = [ScanMode.put_away, ScanMode.pick, ScanMode.lookup] as const;

const MODE_HINTS: Readonly<Record<ScanMode, string>> = {
  put_away: "Erst den Lagerplatz scannen, dann jedes Stück, das dort hineinkommt.",
  pick: "Bestellung wählen, dann jedes Stück der Pickliste scannen.",
  lookup: "Etikett, Platz oder Artikel scannen: zeigt, was dazu im Lager steht. Bucht nichts.",
};

const ENTRY_DOTS: Readonly<Record<ScanEntry["state"], string>> = {
  sending: "bg-line-strong animate-lamp-pulse",
  answered: "bg-success",
  waiting: "bg-warning",
  failed: "bg-danger",
};

function entryDot(entry: ScanEntry): string {
  if (entry.state !== "answered" || entry.answer === undefined) {
    return ENTRY_DOTS[entry.state];
  }
  const tone = scanFeedback(entry.answer);
  return tone === "success" ? "bg-success" : tone === "error" ? "bg-danger" : "bg-ink-tertiary";
}

/** True while the focus is in a field: the keys belong to the field then. */
function isTyping(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement ||
    (target instanceof HTMLElement && target.isContentEditable)
  );
}

type ScannerDeskProps = {
  staffRole: StaffRole;
  /** An order to pick at once (from the order desk's link). */
  initialOrderId: string | null;
  onStreamClosed: () => void;
};

/**
 * The scanner: one page for the phone in the workshop. Camera, hand scanner and
 * keyboard all lead to the same scan; each gets a tone, a flash and a large answer.
 * Without network the scans wait on the device and go out, in order, once it is back.
 */
export function ScannerDesk({ staffRole, initialOrderId, onStreamClosed }: ScannerDeskProps) {
  const queryClient = useQueryClient();
  const [session, setSession] = useState(() =>
    initialSession(initialOrderId ? ScanMode.pick : ScanMode.put_away, initialOrderId),
  );
  const sessionRef = useRef(session);
  const [waiting, setWaiting] = useState(0);
  const [flash, setFlash] = useState<{ tone: FlashTone; key: number } | null>(null);
  const [undoing, setUndoing] = useState<string | null>(null);
  const [manual, setManual] = useState("");
  const store = useRef<ScanStore | null>(null);
  const chain = useRef<Promise<void>>(Promise.resolve());
  const camera = useRef<{ picker: LabelPicker; repeats: RepeatFilter } | null>(null);
  // The count as the send chain sees it (state lags one render behind).
  const waitingRef = useRef(0);
  useEffect(() => {
    waitingRef.current = waiting;
  }, [waiting]);

  // The reducer runs on the ref first, so a scan sent right after an answer already
  // carries the location that answer chose, before React has rendered it.
  const dispatch = useCallback((event: ScanEvent) => {
    sessionRef.current = scanSession(sessionRef.current, event);
    setSession(sessionRef.current);
  }, []);

  const scanStore = useCallback(() => {
    store.current ??= browserScanStore();
    return store.current;
  }, []);

  const feedback = useCallback((tone: FlashTone) => {
    signal(tone);
    setFlash((current) => ({ tone, key: (current?.key ?? 0) + 1 }));
  }, []);

  const refreshAfter = useCallback(
    (answer: ScanOut) => {
      if (answer.mode === ScanMode.pick && sessionRef.current.orderId !== null) {
        void queryClient.invalidateQueries({ queryKey: getGetPickListQueryKey(sessionRef.current.orderId) });
      }
      if (answer.outcome === "applied") {
        void queryClient.invalidateQueries({ queryKey: getListStockQueryKey() });
      }
    },
    [queryClient],
  );

  const deliver = useCallback(
    async (scan: ScanIn) => {
      const answer = await recordScan(scan);
      dispatch({ type: "answered", answer });
      refreshAfter(answer);
      return answer;
    },
    [dispatch, refreshAfter],
  );

  /** Sends the waiting scans; returns how many still wait. */
  const flush = useCallback(async () => {
    const queue = scanStore();
    await flushQueue(
      queue,
      async (scan) => {
        try {
          await deliver(scan);
        } catch (error) {
          if (!isUnreachable(error)) {
            dispatch({ type: "failed", scanId: scan.scan_id, error: errorMessage(error) });
          }
          throw error;
        }
      },
      isUnreachable,
    );
    const left = (await queue.all()).length;
    setWaiting(left);
    return left;
  }, [deliver, dispatch, scanStore]);

  const keepForLater = useCallback(
    async (scan: ScanIn) => {
      try {
        await scanStore().add({ scan, queuedAt: Date.now() });
      } catch {
        dispatch({ type: "failed", scanId: scan.scan_id, error: "Kein Netz, und das Gerät kann den Scan nicht speichern." });
        feedback("error");
        return;
      }
      setWaiting((count) => count + 1);
      dispatch({ type: "waiting", scanId: scan.scan_id });
      const reading = interpretations(scan.raw)[0];
      if (scan.mode === ScanMode.put_away && reading?.kind === "location") {
        dispatch({ type: "assume_location", code: reading.code });
      }
      feedback("info");
    },
    [dispatch, feedback, scanStore],
  );

  const submit = useCallback(
    (raw: string, source: ScanSource) => {
      const text = raw.trim();
      if (text === "") {
        return;
      }
      const scanId = crypto.randomUUID();
      dispatch({ type: "scanned", scanId, raw: text, source, at: Date.now() });
      if (interpretations(text).length === 0) {
        dispatch({ type: "failed", scanId, error: "Das ist kein Code aus dem Lager." });
        feedback("error");
        return;
      }
      if (sessionRef.current.mode === ScanMode.pick && sessionRef.current.orderId === null) {
        dispatch({ type: "failed", scanId, error: "Erst eine Bestellung wählen." });
        feedback("error");
        return;
      }
      // One scan after the other: the answer to a location scan sets the context of the next.
      chain.current = chain.current.then(async () => {
        const current = sessionRef.current;
        const scan: ScanIn = { scan_id: scanId, raw: text, mode: current.mode, source, context: contextFor(current) };
        // Scans that wait go first, so the server sees them in the order they happened.
        if (waitingRef.current > 0 && (await flush()) > 0) {
          await keepForLater(scan);
          return;
        }
        try {
          feedback(scanFeedback(await deliver(scan)));
        } catch (error) {
          if (isUnreachable(error)) {
            await keepForLater(scan);
          } else {
            dispatch({ type: "failed", scanId, error: errorMessage(error) });
            feedback("error");
          }
        }
      });
    },
    [deliver, dispatch, feedback, flush, keepForLater],
  );

  const sendWaiting = useCallback(() => {
    chain.current = chain.current.then(async () => void (await flush()));
  }, [flush]);

  async function undo(scanId: string) {
    setUndoing(scanId);
    try {
      const answer = await undoScan(scanId);
      dispatch({ type: "answered", answer });
      refreshAfter(answer);
      feedback("info");
    } catch (error) {
      dispatch({ type: "failed", scanId, error: errorMessage(error) });
      feedback("error");
    } finally {
      setUndoing(null);
    }
  }

  // Scans left over from an earlier visit: count them and try to send them.
  const startQueue = useEffectEvent(() => {
    void scanStore()
      .all()
      .then((items) => {
        setWaiting(items.length);
        if (items.length > 0) {
          sendWaiting();
        }
      })
      .catch(() => undefined);
  });
  useEffect(() => startQueue(), []);

  const retry = useEffectEvent(() => sendWaiting());
  useEffect(() => {
    window.addEventListener("online", retry);
    const timer = waiting > 0 ? setInterval(retry, RETRY_MS) : undefined;
    return () => {
      window.removeEventListener("online", retry);
      clearInterval(timer);
    };
  }, [waiting]);

  // A hand scanner types into the page; it is recognised by its rhythm.
  const onWedgeScan = useEffectEvent((code: string) => submit(code, "scanner"));
  useEffect(() => {
    const reader = new WedgeReader((code) => onWedgeScan(code));
    const onKey = (event: KeyboardEvent) => {
      if (isTyping(event.target) || event.ctrlKey || event.metaKey || event.altKey) {
        return;
      }
      unlockSound();
      if (reader.feed(event.key, event.timeStamp)) {
        // Keeps the scanner's Enter from pressing whichever button has the focus.
        event.preventDefault();
        event.stopPropagation();
      }
    };
    window.addEventListener("keydown", onKey, true);
    window.addEventListener("pointerdown", unlockSound, { once: true });
    return () => {
      window.removeEventListener("keydown", onKey, true);
      window.removeEventListener("pointerdown", unlockSound);
    };
  }, []);

  const onCameraFrame = (codes: string[], time: number) => {
    camera.current ??= {
      repeats: new RepeatFilter(),
      picker: new LabelPicker((code) => {
        if (camera.current?.repeats.accept(code, performance.now())) {
          submit(code, "camera");
        }
      }),
    };
    camera.current.picker.frame(codes, time);
  };

  const stream = useEventStream({
    url: ADMIN_EVENTS_URL,
    eventTypes: [...INVENTORY_EVENT_TYPES, ...ORDER_EVENT_TYPES],
    onMessage(data) {
      const orderId = sessionRef.current.orderId;
      const stock = stockEventOf(data);
      if (stock !== null && orderId !== null && stock.orderId === orderId) {
        void queryClient.invalidateQueries({ queryKey: getGetPickListQueryKey(orderId) });
      }
      const order = orderEventOf(data);
      if (order !== null) {
        void queryClient.invalidateQueries({ queryKey: [...getListOrdersQueryKey(), "to-pick"] });
        if (order.orderId === orderId) {
          void queryClient.invalidateQueries({ queryKey: getGetPickListQueryKey(orderId) });
        }
      }
    },
    onClosed: onStreamClosed,
  });

  function onManual(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    unlockSound();
    submit(manual, "keyboard");
    setManual("");
  }

  const latest = latestAnswer(session);
  const checking = session.entries.some((entry) => entry.state === "sending");

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="label-caps text-ink-tertiary">Lager</p>
          <h1 className="mt-3 text-heading sm:text-title">Scanner</h1>
        </div>
        <ConnectionLamp state={stream.state} onReconnect={stream.reconnect} />
      </div>

      <OptionGroup
        label="Modus"
        value={session.mode}
        onValueChange={(value) => dispatch({ type: "mode", mode: value as ScanMode })}
        className="mt-6"
      >
        {MODES.map((mode) => (
          <OptionPill key={mode} value={mode}>
            {SCAN_MODE_LABELS[mode]}
          </OptionPill>
        ))}
      </OptionGroup>
      <p className="mt-3 text-small text-ink-secondary">{MODE_HINTS[session.mode]}</p>

      {waiting > 0 ? (
        <div role="status" className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-sm border border-warning bg-warning-subtle px-4 py-3">
          <p className="text-small text-warning">
            <span className="font-medium">{waiting === 1 ? "1 Scan wartet" : `${waiting} Scans warten`}</span> auf das Netz und
            wird nachgereicht.
          </p>
          <Button type="button" size="sm" variant="secondary" onClick={sendWaiting}>
            Jetzt senden
          </Button>
        </div>
      ) : null}

      <div className="mt-6 grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_26rem]">
        <div className="space-y-5">
          {session.mode === ScanMode.put_away ? (
            <PlaceBar code={session.locationCode} name={session.locationName} onLeave={() => dispatch({ type: "leave_location" })} />
          ) : null}
          {session.mode === ScanMode.pick ? (
            <OrderChooser orderId={session.orderId} onChoose={(orderId) => dispatch({ type: "order", orderId })} />
          ) : null}
          <CameraView onFrame={onCameraFrame} onStart={unlockSound} flash={flash} />
          <form onSubmit={onManual} className="flex gap-2" aria-label="Code eintippen">
            <label htmlFor="scan-manual" className="sr-only">
              Code eintippen
            </label>
            <Input
              id="scan-manual"
              value={manual}
              onChange={(event) => setManual(event.target.value)}
              placeholder="Code eintippen, z. B. R01-F02"
              autoComplete="off"
              autoCapitalize="characters"
              spellCheck={false}
              maxLength={300}
              className="font-mono"
            />
            <Button type="submit" variant="secondary" disabled={manual.trim() === ""}>
              Prüfen
            </Button>
          </form>
        </div>

        <div className="space-y-5">
          {latest !== null ? (
            <ScanResult
              entry={latest}
              checking={checking}
              undoing={undoing === latest.scanId}
              onUndo={(scanId) => void undo(scanId)}
            />
          ) : (
            <IdleCard mode={session.mode} />
          )}
          {session.mode === ScanMode.pick && session.orderId !== null ? (
            <PickPanel orderId={session.orderId} mayAllocate={MAY_ALLOCATE.has(staffRole)} />
          ) : null}
          <History entries={session.entries} />
        </div>
      </div>
    </>
  );
}

function IdleCard({ mode }: { mode: ScanMode }) {
  return (
    <div className="rounded-md border border-dashed border-line-strong px-5 py-8 text-center">
      <ScanGlyph className="mx-auto h-10 w-24 text-ink-tertiary" />
      <p className="mt-4 text-small text-ink-secondary">
        {mode === ScanMode.lookup ? "Bereit für eine Auskunft." : "Bereit. Der erste Scan erscheint hier groß."}
      </p>
    </div>
  );
}

/** A barcode with the scanner's red line across it. */
function ScanGlyph({ className }: { className?: string }) {
  const bars = [2, 1, 1, 3, 1, 2, 1, 1, 2, 3, 1, 1, 2, 1, 3, 1, 2];
  let x = 4;
  return (
    <svg aria-hidden="true" viewBox="0 0 96 40" className={className}>
      {bars.map((width, index) => {
        const bar = <rect key={index} x={x} y={4} width={width * 1.6} height={32} fill="currentColor" />;
        x += width * 1.6 + 2.4;
        return bar;
      })}
      <rect x={0} y={19.5} width={96} height={1.2} fill="#ff4d3d" />
    </svg>
  );
}

/** Putting away: the place the next pieces go into, like the route display on a platform. */
function PlaceBar({ code, name, onLeave }: { code: string | null; name: string | null; onLeave: () => void }) {
  if (code === null) {
    return (
      <div className="flex items-center gap-3 rounded-md border border-dashed border-line-control px-4 py-3">
        <span aria-hidden="true" className="font-mono text-heading text-ink-disabled">
          ––––
        </span>
        <p className="text-small text-ink-secondary">Noch kein Platz gewählt: zuerst das Etikett am Fach scannen.</p>
      </div>
    );
  }
  return (
    <div className="flex items-center justify-between gap-4 rounded-md bg-selected px-4 py-3 text-on-selected">
      <div className="min-w-0">
        <p className="label-caps text-on-selected/60">Einlagern nach</p>
        <p className="mt-1 truncate font-mono text-[1.5rem] leading-8 font-medium tracking-wider">{code}</p>
        {name ? <p className="truncate text-small text-on-selected/75">{name}</p> : null}
      </div>
      <Button
        type="button"
        size="sm"
        variant="secondary"
        onClick={onLeave}
        className="border-on-selected/40 text-on-selected hover:border-on-selected hover:bg-on-selected/10"
      >
        Platz wechseln
      </Button>
    </div>
  );
}

const ORDERS_TO_PICK = 50;

/** Picking: the paid orders waiting to be packed, oldest first. */
function OrderChooser({ orderId, onChoose }: { orderId: string | null; onChoose: (orderId: string | null) => void }) {
  const orders = useQuery({
    queryKey: [...getListOrdersQueryKey(), "to-pick"],
    queryFn: ({ signal: abort }) => listOrders({ status: ["paid"], limit: ORDERS_TO_PICK }, { signal: abort }),
    select: (page) => [...page.items].reverse(),
  });
  const items = orders.data ?? [];
  const known = orderId === null || items.some((order) => order.id === orderId);
  return (
    <div>
      <label htmlFor="pick-order" className="label-caps text-ink-tertiary">
        Bestellung
      </label>
      <Select
        id="pick-order"
        className="mt-2"
        value={orderId ?? ""}
        disabled={orders.isPending}
        onChange={(event) => onChoose(event.target.value === "" ? null : event.target.value)}
      >
        <option value="">{orders.isPending ? "Wird geladen …" : items.length === 0 ? "Nichts zu packen" : "Bitte wählen"}</option>
        {!known && orderId !== null ? <option value={orderId}>Gewählte Bestellung</option> : null}
        {items.map((order) => (
          <option key={order.id} value={order.id}>
            {order.number} · {order.recipient} · {order.item_count} Stück
          </option>
        ))}
      </Select>
      {orders.isError ? <p className="mt-2 text-small text-danger">{errorMessage(orders.error)}</p> : null}
    </div>
  );
}

/** The pick list of the chosen order, live; with the button to hand out stock if none was. */
function PickPanel({ orderId, mayAllocate }: { orderId: string; mayAllocate: boolean }) {
  const queryClient = useQueryClient();
  const list = useGetPickList(orderId);
  const [allocating, setAllocating] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  async function allocate() {
    setAllocating(true);
    setProblem(null);
    try {
      queryClient.setQueryData(getGetPickListQueryKey(orderId), await allocateOrder(orderId));
    } catch (error) {
      setProblem(errorMessage(error));
    } finally {
      setAllocating(false);
    }
  }

  if (list.isPending) {
    return <p className="text-small text-ink-secondary">Die Pickliste wird geladen …</p>;
  }
  if (list.isError) {
    return <p className="text-small text-danger">{errorMessage(list.error)}</p>;
  }
  const data = list.data;
  return (
    <section aria-labelledby="pick-heading" className="rounded-md border border-line bg-surface p-5">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="pick-heading" className="text-body font-medium tracking-normal">
          Pickliste <span className="ml-1 font-mono text-small text-ink-secondary">{data.order_number}</span>
        </h2>
        <Link href={`/admin/bestellungen/${orderId}` as Route} className="text-small font-medium text-accent hover:underline">
          Zur Bestellung
        </Link>
      </div>
      <p className="mt-1 text-hint text-ink-tertiary">An {data.ship_recipient}</p>
      {data.allocated ? (
        <>
          <PickProgress list={data} className="mt-4" />
          {data.complete ? (
            <p className="mt-4 rounded-sm bg-success-subtle px-4 py-3 text-small text-success">
              Alles beisammen. Paket packen und in der Bestellung als versendet melden.
            </p>
          ) : null}
          <PickList list={data} linkUnits={false} className="mt-4" />
        </>
      ) : (
        <div className="mt-4 space-y-3">
          <StatusBadge tone="warning">Noch nicht zugeteilt</StatusBadge>
          <p className="text-small text-ink-secondary">
            Bezahlt, aber noch ohne Stücke aus dem Lager. Das System teilt gleich nach der Zahlung zu; hängt es, hilft der Knopf.
          </p>
          {mayAllocate ? (
            <Button type="button" size="sm" onClick={() => void allocate()} disabled={allocating} aria-busy={allocating || undefined}>
              {allocating ? "Wird zugeteilt …" : "Jetzt zuteilen"}
            </Button>
          ) : null}
          {problem ? <p className="text-small text-danger">{problem}</p> : null}
        </div>
      )}
    </section>
  );
}

function History({ entries }: { entries: readonly ScanEntry[] }) {
  if (entries.length <= 1) {
    return null;
  }
  return (
    <section aria-labelledby="history-heading">
      <h2 id="history-heading" className="label-caps text-ink-tertiary">
        Verlauf dieser Sitzung
      </h2>
      <ol className="mt-3 divide-y divide-line border-y border-line">
        {entries.slice(1).map((entry) => (
          <li key={entry.scanId} className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-baseline gap-x-3 py-2.5 animate-feed-in">
            <span aria-hidden="true" className={cn("size-2 translate-y-[-1px] rounded-full", entryDot(entry))} />
            <span className="min-w-0">
              <span className="block truncate font-mono text-hint text-ink-secondary">{entry.raw}</span>
              <span className="block text-small">{entrySummary(entry)}</span>
            </span>
            <time className="font-mono text-hint text-ink-tertiary tabular-nums">{scanTime(entry)}</time>
          </li>
        ))}
      </ol>
    </section>
  );
}
