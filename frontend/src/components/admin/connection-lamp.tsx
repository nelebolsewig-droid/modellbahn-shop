import { Button } from "@/components/ui/button";
import { SignalLamp, type LampColor } from "@/components/ui/signal-lamp";
import type { StreamState } from "@/lib/realtime/use-event-stream";

const SIGNAL: Record<StreamState, { color: LampColor; blinking: boolean; label: string }> = {
  connecting: { color: "yellow", blinking: true, label: "Verbindet …" },
  open: { color: "green", blinking: false, label: "Live verbunden" },
  reconnecting: { color: "yellow", blinking: true, label: "Unterbrochen – verbindet neu …" },
  closed: { color: "red", blinking: false, label: "Keine Verbindung" },
};

type ConnectionLampProps = {
  state: StreamState;
  onReconnect: () => void;
};

/**
 * State of the live connection as a signal lamp: green connected, yellow (blinking)
 * connecting or reconnecting, red failed. The state is also written out, so colour
 * is never the only carrier of the information.
 */
export function ConnectionLamp({ state, onReconnect }: ConnectionLampProps) {
  const signal = SIGNAL[state];
  return (
    <div className="flex items-center gap-3">
      <div role="status" className="flex items-center gap-2">
        <SignalLamp color={signal.color} blinking={signal.blinking} />
        <span className="label-caps">{signal.label}</span>
      </div>
      {state === "closed" ? (
        <Button type="button" variant="secondary" size="sm" onClick={onReconnect}>
          Neu verbinden
        </Button>
      ) : null}
    </div>
  );
}
