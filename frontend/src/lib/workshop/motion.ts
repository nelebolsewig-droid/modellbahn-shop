/**
 * How the crane moves in its three states (ADR 0030): standing, travelling and braking.
 * Pure arithmetic, no three.js: the scene (components/workshop/motion-scene.tsx) and the
 * Blender script (tools/blender/edk6_animation.py) use the same figures.
 *
 * What moves is what the print files hold as parts of their own: the superstructure slews
 * on its ring, the rope flap opens on its hinge, the bogies turn a little under the frame,
 * the whole crane travels and nods when it brakes. The wheels are printed in one piece
 * with the bogie frames, so they cannot turn; the track running past shows the travel.
 */

export type MotionMode = "idle" | "moving" | "braking";

export type MotionState = {
  /** Seconds in the current mode. */
  time: number;
  /** Travel speed in metres of the original per second. */
  speed: number;
  /** Distance travelled, metres of the original. */
  travel: number;
  /** Angles in radians: superstructure about the ring, flap about its hinge, the frame's nod, the bogies' turn. */
  slew: number;
  flap: number;
  pitch: number;
  bogieYaw: number;
};

export const MOTION = {
  /** Walking pace: a crane moving itself on the work site, 5 km/h. */
  cruiseSpeed: 5 / 3.6,
  /** Reaching it takes 2.5 s, stopping from it 1.6 s. */
  acceleration: 5 / 3.6 / 2.5,
  deceleration: 5 / 3.6 / 1.6,
  /** Standing, the superstructure swings 35° to each side, once in 12 s. */
  slewAmplitude: (35 * Math.PI) / 180,
  slewPeriod: 12,
  /** The flap opens to 55° and closes again, once in 6 s. */
  flapOpen: (55 * Math.PI) / 180,
  flapPeriod: 6,
  /** Braking tips the frame forward by up to 1.2°. */
  pitchMax: (1.2 * Math.PI) / 180,
  /** Travelling, the bogies hunt by 1.5°, 1.4 times a second. */
  bogieYaw: (1.5 * Math.PI) / 180,
  bogieFrequency: 1.4,
  /** How quickly an angle follows its target (1/s). */
  follow: 4,
} as const;

export const RESTING: MotionState = { time: 0, speed: 0, travel: 0, slew: 0, flap: 0, pitch: 0, bogieYaw: 0 };

const towards = (value: number, target: number, seconds: number, rate: number = MOTION.follow) =>
  value + (target - value) * Math.min(1, seconds * rate);

/** The state after `seconds` more in `mode`. A change of mode starts its clock at 0. */
export function stepMotion(state: MotionState, mode: MotionMode, seconds: number, changed = false): MotionState {
  const time = changed ? 0 : state.time + seconds;
  let { speed } = state;
  let slewTarget = 0;
  let flapTarget = 0;
  let pitchTarget = 0;
  let bogieTarget = 0;

  if (mode === "idle") {
    speed = Math.max(0, speed - MOTION.deceleration * seconds);
    slewTarget = MOTION.slewAmplitude * Math.sin((2 * Math.PI * time) / MOTION.slewPeriod);
    flapTarget = (MOTION.flapOpen * (1 - Math.cos((2 * Math.PI * time) / MOTION.flapPeriod))) / 2;
  } else if (mode === "moving") {
    speed = Math.min(MOTION.cruiseSpeed, speed + MOTION.acceleration * seconds);
    bogieTarget =
      MOTION.bogieYaw * (speed / MOTION.cruiseSpeed) * Math.sin(2 * Math.PI * MOTION.bogieFrequency * time);
  } else {
    const before = speed;
    speed = Math.max(0, speed - MOTION.deceleration * seconds);
    // The nod follows how hard the brakes bite, and goes when the crane stands.
    pitchTarget = before > 0 && speed > 0 ? MOTION.pitchMax : 0;
  }

  return {
    time,
    speed,
    travel: state.travel + speed * seconds,
    slew: towards(state.slew, slewTarget, seconds, mode === "idle" ? MOTION.follow : 1.5),
    flap: towards(state.flap, flapTarget, seconds),
    pitch: towards(state.pitch, pitchTarget, seconds, 6),
    bogieYaw: towards(state.bogieYaw, bogieTarget, seconds, 8),
  };
}
