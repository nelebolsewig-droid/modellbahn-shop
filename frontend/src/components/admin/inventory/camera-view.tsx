"use client";

import { useEffect, useEffectEvent, useRef, useState, type RefObject } from "react";

import { Button } from "@/components/ui/button";
import {
  cameraProblem,
  createCodeDetector,
  openBackCamera,
  setTorch,
  supportsTorch,
  type CameraProblem,
  type CodeDetector,
} from "@/lib/inventory/camera";
import { cn } from "@/lib/utils";

/** Pause between two looks at the picture: fast enough to feel instant, light on the battery. */
const FRAME_INTERVAL_MS = 120;

type CameraState =
  | { phase: "off" }
  | { phase: "starting" }
  | { phase: "running"; torch: boolean | null }
  | { phase: "problem"; problem: CameraProblem };

const PROBLEMS: Readonly<Record<CameraProblem, string>> = {
  denied: "Der Browser darf die Kamera nicht benutzen. In den Website-Einstellungen erlauben und erneut starten.",
  missing: "Dieses Gerät hat keine passende Kamera. Handscanner oder Eingabe benutzen.",
  insecure: "Die Kamera geht nur über eine sichere Verbindung (https).",
  failed: "Die Kamera ließ sich nicht starten. Erneut versuchen oder Handscanner benutzen.",
};

export type FlashTone = "success" | "error" | "info";

/** Switches the camera off and lets go of the picture. */
function release(stream: RefObject<MediaStream | null>, video: RefObject<HTMLVideoElement | null>): void {
  stream.current?.getTracks().forEach((track) => track.stop());
  stream.current = null;
  if (video.current) {
    video.current.srcObject = null;
  }
}

type CameraViewProps = {
  /** Every code found in one frame, possibly none; called once per frame. */
  onFrame: (codes: string[], time: number) => void;
  /** Called from the tap that starts the camera (lets the page unlock its sound). */
  onStart?: () => void;
  /** Lights the frame up after a scan; a new `key` lights it again. */
  flash: { tone: FlashTone; key: number } | null;
  className?: string;
};

/**
 * The viewfinder: the back camera, a frame to aim with, and a coloured flash after each
 * scan. Starts only on a tap (browsers ask for permission then) and stops when the page
 * goes into the background, so a phone in the apron pocket does not film the lining.
 */
export function CameraView({ onFrame, onStart, flash, className }: CameraViewProps) {
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const detector = useRef<CodeDetector | null>(null);
  const [state, setState] = useState<CameraState>({ phase: "off" });
  const handleFrame = useEffectEvent(onFrame);

  const stop = () => {
    release(stream, video);
    setState({ phase: "off" });
  };

  async function start() {
    onStart?.();
    setState({ phase: "starting" });
    const [camera, reader] = await Promise.allSettled([openBackCamera(), createCodeDetector()]);
    if (camera.status === "rejected" || reader.status === "rejected") {
      if (camera.status === "fulfilled") {
        camera.value.getTracks().forEach((track) => track.stop());
      }
      setState({ phase: "problem", problem: camera.status === "rejected" ? cameraProblem(camera.reason) : "failed" });
      return;
    }
    stream.current = camera.value;
    detector.current = reader.value;
    const element = video.current;
    if (element === null) {
      stop();
      return;
    }
    element.srcObject = camera.value;
    try {
      await element.play();
    } catch {
      release(stream, video);
      setState({ phase: "problem", problem: "failed" });
      return;
    }
    setState({ phase: "running", torch: supportsTorch(camera.value.getVideoTracks()[0]) ? false : null });
  }

  async function toggleTorch() {
    const track = stream.current?.getVideoTracks()[0];
    if (state.phase !== "running" || state.torch === null || track === undefined) {
      return;
    }
    const next = !state.torch;
    try {
      await setTorch(track, next);
      setState({ phase: "running", torch: next });
    } catch {
      setState({ phase: "running", torch: null });
    }
  }

  const running = state.phase === "running";

  useEffect(() => {
    if (!running) {
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const look = async () => {
      const element = video.current;
      const reader = detector.current;
      if (element !== null && reader !== null && element.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
        try {
          const found = await reader.detect(element);
          if (!cancelled) {
            handleFrame(
              found.map((code) => code.rawValue),
              performance.now(),
            );
          }
        } catch {
          // A frame the reader could not take (e.g. while the camera refocuses): next one.
        }
      }
      if (!cancelled) {
        timer = setTimeout(() => void look(), FRAME_INTERVAL_MS);
      }
    };
    void look();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [running]);

  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState === "hidden") {
        release(stream, video);
        setState({ phase: "off" });
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      release(stream, video);
    };
  }, []);

  return (
    <div className={cn("overflow-hidden rounded-md border border-line bg-viewfinder text-on-viewfinder", className)}>
      <div className="relative aspect-[4/3] sm:aspect-video">
        <video
          ref={video}
          muted
          playsInline
          aria-label="Kamerabild"
          className={cn("absolute inset-0 size-full object-cover transition-opacity", running ? "opacity-100" : "opacity-0")}
        />
        <Viewfinder active={running} />
        {flash !== null ? <Flash key={flash.key} tone={flash.tone} /> : null}
        {!running ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 p-6 text-center">
            {state.phase === "problem" ? (
              <p role="alert" className="max-w-sm text-small text-on-viewfinder">
                {PROBLEMS[state.problem]}
              </p>
            ) : (
              <p className="max-w-xs text-small text-on-viewfinder-muted">
                Etikett in den Rahmen halten. Ein Handscanner funktioniert jederzeit, auch ohne Kamera.
              </p>
            )}
            <Button
              type="button"
              variant="secondary"
              disabled={state.phase === "starting"}
              aria-busy={state.phase === "starting" || undefined}
              onClick={() => void start()}
              className="border-on-viewfinder/40 bg-on-viewfinder/10 text-on-viewfinder hover:border-on-viewfinder hover:bg-on-viewfinder/20"
            >
              {state.phase === "starting" ? "Kamera startet …" : state.phase === "problem" ? "Erneut versuchen" : "Kamera starten"}
            </Button>
          </div>
        ) : null}
      </div>
      {running ? (
        <div className="flex items-center justify-between gap-3 border-t border-on-viewfinder/10 px-4 py-2.5">
          <p className="flex items-center gap-2 text-hint text-on-viewfinder-muted">
            <span aria-hidden="true" className="size-1.5 animate-lamp-pulse rounded-full bg-aim" />
            Kamera sucht
          </p>
          <div className="flex gap-2">
            {state.torch !== null ? (
              <Button
                type="button"
                size="sm"
                variant="secondary"
                aria-pressed={state.torch}
                onClick={() => void toggleTorch()}
                className="border-on-viewfinder/30 bg-transparent text-on-viewfinder hover:border-on-viewfinder hover:bg-on-viewfinder/10 aria-pressed:bg-on-viewfinder aria-pressed:text-ink"
              >
                Licht
              </Button>
            ) : null}
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={stop}
              className="border-on-viewfinder/30 bg-transparent text-on-viewfinder hover:border-on-viewfinder hover:bg-on-viewfinder/10"
            >
              Kamera aus
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/** Corner marks and a red aiming line, like the window of a hand scanner. */
function Viewfinder({ active }: { active: boolean }) {
  const corner = "absolute size-7 border-on-viewfinder/90";
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-[12%_10%]">
      <span className={cn(corner, "top-0 left-0 rounded-tl-sm border-t-2 border-l-2")} />
      <span className={cn(corner, "top-0 right-0 rounded-tr-sm border-t-2 border-r-2")} />
      <span className={cn(corner, "bottom-0 left-0 rounded-bl-sm border-b-2 border-l-2")} />
      <span className={cn(corner, "right-0 bottom-0 rounded-br-sm border-r-2 border-b-2")} />
      <span
        className={cn(
          "absolute inset-x-3 top-1/2 h-px -translate-y-1/2 bg-aim shadow-[0_0_8px_1px_var(--aim)] transition-opacity",
          active ? "animate-lamp-pulse opacity-100" : "opacity-30",
        )}
      />
    </div>
  );
}

const FLASH_COLOURS: Readonly<Record<FlashTone, string>> = {
  success: "shadow-[inset_0_0_0_6px_var(--success)] bg-success/15",
  error: "shadow-[inset_0_0_0_6px_var(--danger)] bg-danger/20",
  info: "shadow-[inset_0_0_0_6px_var(--accent-subtle)] bg-on-viewfinder/10",
};

function Flash({ tone }: { tone: FlashTone }) {
  return <span aria-hidden="true" className={cn("pointer-events-none absolute inset-0 animate-scan-flash", FLASH_COLOURS[tone])} />;
}
