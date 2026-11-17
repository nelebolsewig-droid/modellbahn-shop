// @vitest-environment node

import { describe, expect, it } from "vitest";

import { MOTION, RESTING, stepMotion, type MotionMode, type MotionState } from "./motion";

function run(state: MotionState, mode: MotionMode, seconds: number): MotionState {
  let next = stepMotion(state, mode, 0, true);
  for (let passed = 0; passed < seconds; passed += 1 / 60) next = stepMotion(next, mode, 1 / 60);
  return next;
}

describe("the crane's motion", () => {
  it("stands still while it idles, slewing and opening its flap", () => {
    const quarter = run(RESTING, "idle", MOTION.slewPeriod / 4);
    expect(quarter.speed).toBe(0);
    expect(quarter.travel).toBe(0);
    expect(quarter.slew).toBeGreaterThan(MOTION.slewAmplitude * 0.8);
    expect(run(RESTING, "idle", MOTION.flapPeriod / 2).flap).toBeGreaterThan(MOTION.flapOpen * 0.8);
  });

  it("reaches walking pace in 2.5 s and keeps it", () => {
    expect(run(RESTING, "moving", 1).speed).toBeLessThan(MOTION.cruiseSpeed);
    const cruising = run(RESTING, "moving", 4);
    expect(cruising.speed).toBeCloseTo(MOTION.cruiseSpeed, 5);
    expect(cruising.travel).toBeGreaterThan(3);
  });

  it("turns the superstructure back and shuts the flap before it travels far", () => {
    const swung = run(RESTING, "idle", 3);
    const travelling = run(swung, "moving", 5);
    expect(Math.abs(travelling.slew)).toBeLessThan(0.01);
    expect(travelling.flap).toBeLessThan(0.01);
  });

  it("stops within 1.6 s, nods while it brakes and settles", () => {
    const cruising = run(RESTING, "moving", 4);
    const biting = run(cruising, "braking", 0.8);
    expect(biting.speed).toBeGreaterThan(0);
    expect(biting.pitch).toBeGreaterThan(MOTION.pitchMax * 0.8);
    const stopped = run(cruising, "braking", 3);
    expect(stopped.speed).toBe(0);
    expect(stopped.pitch).toBeLessThan(MOTION.pitchMax * 0.05);
    expect(stopped.travel - cruising.travel).toBeCloseTo((MOTION.cruiseSpeed * 1.6) / 2, 1);
  });
});
