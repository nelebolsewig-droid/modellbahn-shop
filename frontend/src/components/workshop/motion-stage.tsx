"use client";

import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";

import type { ExplosionModel } from "@/lib/workshop/explosion";
import type { MotionMode } from "@/lib/workshop/motion";
import { cn } from "@/lib/utils";

import { useNearViewport, useReducedMotion } from "./explosion-view";

const MotionScene = lazy(() => import("./motion-scene"));

const MODES: readonly { mode: MotionMode; label: string; text: string; seconds: number }[] = [
  { mode: "idle", label: "Stand", text: "Der Oberwagen schwenkt, die Seilklappe öffnet sich.", seconds: 7 },
  { mode: "moving", label: "Fahrt", text: "Der Kran fährt im Schritttempo, die Drehgestelle arbeiten.", seconds: 7 },
  { mode: "braking", label: "Bremsen", text: "Der Kran kommt zum Stehen und nickt dabei leicht ein.", seconds: 3.5 },
];

/**
 * The workshop's crane in motion on the night ground: standing, travelling, braking. It
 * runs through the three states by itself until the visitor picks one. With reduced
 * motion it stands still; without WebGL the section says so.
 */
export function MotionStage({ model }: { model: ExplosionModel }) {
  const reducedMotion = useReducedMotion();
  const stageRef = useRef<HTMLDivElement>(null);
  const mode = useRef<MotionMode>("idle");
  const [shown, setShown] = useState<MotionMode>("idle");
  const [auto, setAuto] = useState(true);
  const [speed, setSpeed] = useState(0);
  const [unavailable, setUnavailable] = useState(false);
  const near = useNearViewport(stageRef);
  const onUnavailable = useCallback(() => setUnavailable(true), []);
  const onSpeed = useCallback((value: number) => setSpeed(Math.round(value * 3.6 * 10) / 10), []);

  const show = useCallback((next: MotionMode) => {
    mode.current = next;
    setShown(next);
  }, []);

  // The demonstration: each state for its time, then the next.
  useEffect(() => {
    if (!auto || reducedMotion || !near) return;
    const current = MODES.findIndex((entry) => entry.mode === shown);
    const timer = window.setTimeout(
      () => show(MODES[(current + 1) % MODES.length]?.mode ?? "idle"),
      (MODES[current]?.seconds ?? 5) * 1000,
    );
    return () => window.clearTimeout(timer);
  }, [auto, reducedMotion, near, shown, show]);

  const active = MODES.find((entry) => entry.mode === shown);
  return (
    <div className="relative overflow-hidden rounded-lg bg-night text-on-night">
      <span aria-hidden="true" className="absolute -top-32 right-0 size-[28rem] animate-drift rounded-full bg-plum opacity-50 blur-[90px]" />
      <span aria-hidden="true" className="absolute -bottom-40 -left-24 size-[26rem] animate-drift-slow rounded-full bg-sea opacity-45 blur-[90px]" />
      <div ref={stageRef} className="relative aspect-[4/5] sm:aspect-[16/10]">
        {near && !unavailable ? (
          <Suspense fallback={null}>
            <MotionScene model={model} mode={mode} onSpeed={onSpeed} still={reducedMotion} onUnavailable={onUnavailable} />
          </Suspense>
        ) : null}
        {unavailable ? (
          <p className="absolute inset-0 grid place-items-center p-6 text-center text-small text-on-night-muted">
            Die 3D-Ansicht braucht WebGL.
          </p>
        ) : null}
        <p aria-hidden="true" className="absolute top-4 right-4 rounded-full border border-on-night/20 bg-on-night/10 px-3 py-1 font-mono text-hint tabular-nums backdrop-blur">
          {speed.toFixed(1).replace(".", ",")} km/h
        </p>
      </div>
      <div className="relative flex flex-wrap items-center justify-between gap-4 border-t border-on-night/15 px-5 py-4 sm:px-7">
        <div role="group" aria-label="Zustand des Krans" className="flex gap-1.5">
          {MODES.map((entry) => (
            <button
              key={entry.mode}
              type="button"
              aria-pressed={shown === entry.mode}
              disabled={reducedMotion}
              onClick={() => {
                setAuto(false);
                show(entry.mode);
              }}
              className={cn(
                "h-10 cursor-pointer rounded-full px-4 text-small font-medium outline-on-night transition-colors duration-150",
                "disabled:cursor-not-allowed disabled:opacity-60",
                shown === entry.mode ? "bg-sun text-ink" : "border border-on-night/30 hover:bg-on-night/10",
              )}
            >
              {entry.label}
            </button>
          ))}
        </div>
        <p role="status" className="text-small text-on-night-muted">
          {reducedMotion ? "Die Bewegung ist angehalten, weil dein Gerät reduzierte Bewegung wünscht." : active?.text}
        </p>
      </div>
    </div>
  );
}
