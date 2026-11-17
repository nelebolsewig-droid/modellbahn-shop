"use client";

import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";

import type { ExplosionModel } from "@/lib/workshop/explosion";
import { cn } from "@/lib/utils";

import { useNearViewport, useReducedMotion } from "./explosion-view";

const ExplosionScene = lazy(() => import("./explosion-scene"));

// How far the model comes apart under the pointer, and how fast it follows (per second).
const OPENED = 0.62;
const FOLLOW = 3.2;

const NOTHING = () => {};

/**
 * A model turning on the drawing sheet, in its paint: the start page's look into the
 * workshop. Under the pointer (or a finger) it comes apart, and goes back together when
 * left alone. Decorative: the page it leads to has the parts list. Loads three.js only
 * when it comes near the viewport, and shows nothing where WebGL is missing.
 */
// The drawing's colours on the night ground: pale faces, light-blue edges.
const NIGHT = { fill: "#eef3f7", line: "#8fa9c0" } as const;

type ModelTurntableProps = { model: ExplosionModel; ground?: "sheet" | "night"; zoom?: number; className?: string };

export function ModelTurntable({ model, ground = "sheet", zoom = 1, className }: ModelTurntableProps) {
  const reducedMotion = useReducedMotion();
  const stageRef = useRef<HTMLDivElement>(null);
  const explosion = useRef(0);
  const target = useRef(0);
  const [unavailable, setUnavailable] = useState(false);
  const near = useNearViewport(stageRef);
  const onUnavailable = useCallback(() => setUnavailable(true), []);

  useEffect(() => {
    if (reducedMotion) return;
    let frame = 0;
    let last = performance.now();
    const step = (now: number) => {
      const seconds = Math.min(0.05, (now - last) / 1000);
      last = now;
      explosion.current += (target.current - explosion.current) * Math.min(1, seconds * FOLLOW);
      frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [reducedMotion]);

  if (unavailable) return null;
  return (
    <div
      ref={stageRef}
      aria-hidden="true"
      onPointerEnter={() => (target.current = OPENED)}
      onPointerLeave={() => (target.current = 0)}
      className={cn("relative aspect-[4/3] w-full", className)}
    >
      {near ? (
        <Suspense fallback={null}>
          <ExplosionScene
            model={model}
            explosion={explosion}
            highlighted={null}
            onHighlight={NOTHING}
            spinning={!reducedMotion}
            palette={ground === "night" ? NIGHT : undefined}
            zoom={zoom}
            plain
            onUnavailable={onUnavailable}
          />
        </Suspense>
      ) : null}
    </div>
  );
}
