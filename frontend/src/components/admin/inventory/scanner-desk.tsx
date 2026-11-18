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
import { ScanMode, type ScanIn, type ScanOut, type ScrapReason, type StaffRole } from "@/lib/api/generated/model";
import { interpretations } from "@/lib/inventory/codes";
import { signal, unlockSound } from "@/lib/inventory/feedback";
import { scanFeedback, SCAN_MODE_LABELS, SCRAP_REASON_LABELS } from "@/lib/inventory/labels";
import { browserScanStore, flushQueue, isUnreachable, type ScanStore } from "@/lib/inventory/scan-queue";
import {
  contextFor,
  COUNTING_MODES,
  initialSession,
  latestAnswer,
  modeOf,
  quantityOf,
  SCAN_QUANTITY_MAX,
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
import { SCRAP_REASONS } from "@/lib/validation/inventory";

import { CameraView, type FlashTone } from "./camera-view";
import { PickList, PickProgress } from "./pick-list";
import { entrySummary, ScanResult, scanTime } from "./scan-result";

/** Owner and staff may hand out stock to an order and book it out; packers pick and put away. */
const MAY_ALLOCATE: ReadonlySet<StaffRole> = new Set(["owner", "staff"]);

/** How often waiting scans try again while the network is gone. */
const RETRY_MS = 20_000;

const MODES = [ScanMode.put_away, ScanMode.pick, ScanMode.scrap, ScanMode.lookup] as const;

const AUTO = "auto";

const AUTO_HINT =
  "Einfach scannen. Ein Platz öffnet ihn zum Einlagern, jedes Etikett danach kommt hinein. Ein Etikett ohne Platz zeigt, was dazu im Lager steht.";

const MODE_HINTS: Readonly<Record<ScanMode, string>> = {
  put_away:
    "Erst den Platz scannen, dann das Etikett des Modells: Die Anzahl sagt, wie viele Stücke es sind. Ein Teileetikett bringt die Teile aus dem Wareneingang hinein.",
  pick: "Bestellung wählen, dann für jedes Stück der Pickliste das Etikett des Modells scannen.",
  scrap:
    "Grund und Anzahl wählen, dann das Etikett des Modells scannen. Mit Platz gehen die Stücke dort hinaus, sonst die ältesten freien.",
  lookup: "Etikett, Platz, Modell oder Teil scannen: zeigt, was dazu im Lager steht. Bucht nichts.",
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
    initialSession(initialOrderId ? ScanMode.pick : "auto", initialOrderId),
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
      if (COUNTING_MODES.has(scan.mode) && reading?.kind === "location") {
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
      // The scan takes the Anzahl along now, and the field is back at 1 for the next one.
      dispatch({ type: "scanned", scanId, raw: text, source, at: Date.now() });
      const quantity = quantityOf(sessionRef.current, scanId);
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
        // An automatic scan chose its mode when it was scanned; the context follows it.
        const mode = modeOf(sessionRef.current, scanId);
        const current = { ...sessionRef.current, mode };
        const scan: ScanIn = {
          scan_id: scanId,
          raw: text,
          mode,
          source,
          // A location opened automatically is not the context of its own scan.
          context: contextFor(
            current.auto && interpretations(text)[0]?.kind === "location" ? { ...current, locationCode: null } : current,
          ),
          quantity,
        };
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
  const modes = MODES.filter((mode) => mode !== ScanMode.scrap || MAY_ALLOCATE.has(staffRole));

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="label-caps text-ink-tertiary">Lager</p>
          <h1 className="mt-3 text-heading sm:text-title">Scannen</h1>
        </div>
        <ConnectionLamp state={stream.state} onReconnect={stream.reconnect} />
      </div>

      <OptionGroup
        label="Modus"
        value={session.auto ? AUTO : session.mode}
        onValueChange={(value) =>
          dispatch(value === AUTO ? { type: "auto" } : { type: "mode", mode: value as ScanMode })
        }
        className="mt-6"
      >
        <OptionPill value={AUTO}>Automatisch</OptionPill>
        {modes.map((mode) => (
          <OptionPill key={mode} value={mode}>
            {SCAN_MODE_LABELS[mode]}
          </OptionPill>
        ))}
      </OptionGroup>
      <p className="mt-3 text-small text-ink-secondary">{session.auto ? AUTO_HINT : MODE_HINTS[session.mode]}</p>

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
          {session.mode === ScanMode.pick ? (
            <OrderChooser orderId={session.orderId} onChoose={(orderId) => dispatch({ type: "order", orderId })} />
          ) : null}
          {/* The camera comes first: on the phone it is what the scanner page is for. */}
          <CameraView onFrame={onCameraFrame} onStart={unlockSound} flash={flash} />
          {session.mode === ScanMode.scrap ? (
            <ReasonChooser reason={session.reason} onChoose={(reason) => dispatch({ type: "reason", reason })} />
          ) : null}
          {COUNTING_MODES.has(session.mode) ? (
            <PlaceBar
              mode={session.mode === ScanMode.scrap ? "scrap" : session.auto ? "auto" : "put_away"}
              code={session.locationCode}
              name={session.locationName}
              onLeave={() => dispatch({ type: "leave_location" })}
            />
          ) : null}
          {COUNTING_MODES.has(session.mode) && (!session.auto || session.locationCode !== null) ? (
            <CountField
              key={session.quantity}
              value={session.quantity}
              onChange={(quantity) => dispatch({ type: "quantity", quantity })}
              onCode={(code) => submit(code, "scanner")}
            />
          ) : null}
          <form onSubmit={onManual} className="flex gap-2" aria-label="Code eintippen">
            <label htmlFor="scan-manual" className="sr-only">
              Code eintippen
            </label>
            <Input
              id="scan-manual"
              value={manual}
              onChange={(event) => setManual(event.target.value)}
              placeholder="Code eintippen"
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
            <IdleCard mode={session.auto ? null : session.mode} />
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

function IdleCard({ mode }: { mode: ScanMode | null }) {
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
      <rect x={0} y={19.5} width={96} height={1.2} fill="var(--aim)" />
    </svg>
  );
}

/** Booking out: why the pieces leave. The select lets go of the focus at once, so the
 * hand scanner's next code does not pick another reason by typing. */
function ReasonChooser({ reason, onChoose }: { reason: ScrapReason; onChoose: (reason: ScrapReason) => void }) {
  return (
    <div>
      <label htmlFor="scrap-reason" className="label-caps text-ink-tertiary">
        Grund
      </label>
      <Select
        id="scrap-reason"
        className="mt-2"
        value={reason}
        onChange={(event) => {
          onChoose(event.target.value as ScrapReason);
          event.target.blur();
        }}
      >
        {SCRAP_REASONS.map((value) => (
          <option key={value} value={value}>
            {SCRAP_REASON_LABELS[value]}
          </option>
        ))}
      </Select>
    </div>
  );
}

/**
 * How many pieces the next model label stands for: minus, number, plus. Taken over with
 * Enter or when the field is left. A hand scanner that types into the field by mistake is
 * recognised by its rhythm: its code is scanned, the number typed before it stays.
 */
function CountField({
  value,
  onChange,
  onCode,
}: {
  value: number;
  onChange: (quantity: number) => void;
  onCode: (code: string) => void;
}) {
  const [draft, setDraft] = useState(String(value));
  const reader = useRef<{ wedge: WedgeReader; code: string | null } | null>(null);
  // Set while a scan typed into the field is handled: leaving the field then takes nothing.
  const scanned = useRef(false);
  const take = (text: string) => {
    const quantity = Number.parseInt(text, 10);
    if (Number.isInteger(quantity) && quantity >= 1 && quantity <= SCAN_QUANTITY_MAX && quantity !== value) {
      onChange(quantity);
    } else {
      setDraft(String(value));
    }
  };
  const step = (delta: number) => onChange(Math.min(SCAN_QUANTITY_MAX, Math.max(1, value + delta)));
  return (
    <div>
      <label htmlFor="scan-quantity" className="label-caps text-ink-tertiary">
        Anzahl
      </label>
      <div className="mt-2 flex items-center gap-2">
        <Button type="button" variant="secondary" aria-label="Eins weniger" disabled={value <= 1} onClick={() => step(-1)}>
          −
        </Button>
        <Input
          id="scan-quantity"
          value={draft}
          onChange={(event) => setDraft(event.target.value.replace(/\D/g, ""))}
          onFocus={(event) => event.target.select()}
          onBlur={() => {
            if (scanned.current) {
              scanned.current = false;
            } else {
              take(draft);
            }
          }}
          onKeyDown={(event) => {
            reader.current ??= {
              code: null,
              wedge: new WedgeReader((code) => {
                if (reader.current) {
                  reader.current.code = code;
                }
              }),
            };
            if (reader.current.wedge.feed(event.key, event.timeStamp)) {
              event.preventDefault();
              const code = reader.current.code ?? "";
              reader.current.code = null;
              // The field keeps digits only: what the person typed is what comes before
              // the code's digits.
              const digits = code.replace(/\D/g, "");
              take(draft.endsWith(digits) ? draft.slice(0, draft.length - digits.length) : "");
              onCode(code);
              scanned.current = true;
              event.currentTarget.blur();
            } else if (event.key === "Enter") {
              event.preventDefault();
              event.currentTarget.blur();
            }
          }}
          inputMode="numeric"
          autoComplete="off"
          aria-describedby="scan-quantity-hint"
          className="w-24 text-center font-mono tabular-nums"
        />
        <Button
          type="button"
          variant="secondary"
          aria-label="Eins mehr"
          disabled={value >= SCAN_QUANTITY_MAX}
          onClick={() => step(1)}
        >
          +
        </Button>
        <p id="scan-quantity-hint" className="min-w-0 text-hint text-ink-tertiary">
          {value === 1 ? "Stück je Etikett" : "Stücke für das nächste Etikett, danach wieder 1"}
        </p>
      </div>
    </div>
  );
}

/** Putting away: the place the next pieces go into, like the route display on a platform.
 * Booking out: the place they leave, or none (the oldest free pieces, wherever they lie). */
function PlaceBar({
  mode,
  code,
  name,
  onLeave,
}: {
  mode: "auto" | "put_away" | "scrap";
  code: string | null;
  name: string | null;
  onLeave: () => void;
}) {
  if (code === null) {
    return (
      <div className="flex items-center gap-3 rounded-md border border-dashed border-line-control px-4 py-3">
        <span aria-hidden="true" className="font-mono text-heading text-ink-disabled">
          {mode === "scrap" ? "alle" : mode === "auto" ? "frei" : "leer"}
        </span>
        <p className="text-small text-ink-secondary">
          {mode === "scrap"
            ? "Ohne Platz: die ältesten freien Stücke, wo sie auch liegen. Für einen Platz sein Etikett scannen."
            : mode === "auto"
              ? "Kein Platz offen: Ein Etikett zeigt, was dazu im Lager steht. Zum Einlagern zuerst das Fach scannen."
              : "Noch kein Platz gewählt: zuerst das Etikett am Fach scannen."}
        </p>
      </div>
    );
  }
  return (
    <div className="flex items-center justify-between gap-4 rounded-md bg-selected px-4 py-3 text-on-selected">
      <div className="min-w-0">
        <p className="label-caps text-on-selected/60">{mode === "scrap" ? "Ausbuchen aus" : "Einlagern nach"}</p>
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
        {mode === "scrap" ? "Ohne Platz" : mode === "auto" ? "Platz schließen" : "Platz wechseln"}
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
          <PickList list={data} className="mt-4" />
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
