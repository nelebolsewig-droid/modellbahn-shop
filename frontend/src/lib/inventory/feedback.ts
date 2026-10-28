/*
 * What a scan sounds and feels like, so the packer need not look at the phone:
 * a bright double tone when it worked, a low buzz when it did not, a click for a lookup.
 * Browsers only play sound after a user gesture; the scanner page calls `unlockSound`
 * from its first tap.
 */

type Tone = "success" | "error" | "info";

let context: AudioContext | null = null;

function audio(): AudioContext | null {
  if (typeof window === "undefined" || typeof window.AudioContext === "undefined") {
    return null;
  }
  context ??= new window.AudioContext();
  return context;
}

/** Allows sound from now on (call from a click or tap). */
export function unlockSound(): void {
  void audio()?.resume();
}

function beep(ctx: AudioContext, frequency: number, start: number, duration: number, type: OscillatorType): void {
  const oscillator = ctx.createOscillator();
  const gain = ctx.createGain();
  oscillator.type = type;
  oscillator.frequency.value = frequency;
  gain.gain.setValueAtTime(0.0001, start);
  gain.gain.exponentialRampToValueAtTime(0.25, start + 0.01);
  gain.gain.exponentialRampToValueAtTime(0.0001, start + duration);
  oscillator.connect(gain).connect(ctx.destination);
  oscillator.start(start);
  oscillator.stop(start + duration + 0.02);
}

const VIBRATION: Readonly<Record<Tone, number[]>> = {
  success: [40],
  error: [120, 60, 120],
  info: [15],
};

/** Plays the tone and vibrates (where the device can). */
export function signal(tone: Tone): void {
  const ctx = audio();
  if (ctx !== null && ctx.state === "running") {
    const now = ctx.currentTime;
    if (tone === "success") {
      beep(ctx, 1320, now, 0.08, "sine");
      beep(ctx, 1760, now + 0.09, 0.1, "sine");
    } else if (tone === "error") {
      beep(ctx, 220, now, 0.32, "square");
    } else {
      beep(ctx, 880, now, 0.04, "sine");
    }
  }
  if (typeof navigator !== "undefined" && typeof navigator.vibrate === "function") {
    navigator.vibrate(VIBRATION[tone]);
  }
}
