/*
 * Where scans come from besides the camera, and how repeats are kept out.
 *
 * A hand scanner (USB or Bluetooth, as at Johann's till) types like a keyboard: the
 * characters of the code in quick succession, then Enter. People type far slower, so
 * the rhythm tells them apart: at least six characters, each less than 35 ms after the
 * one before. While the focus is in a text field the field gets the keys instead.
 */

import { isValidEan13 } from "./codes";

export const WEDGE_MIN_LENGTH = 6;
export const WEDGE_MAX_GAP_MS = 35;
/** A camera reads the same label many times a second; it counts once in this window. */
export const REPEAT_WINDOW_MS = 1500;

/** Collects the keystrokes of a hand scanner and reports each complete code. */
export class WedgeReader {
  private buffer = "";
  private last = Number.NEGATIVE_INFINITY;

  constructor(
    private readonly onScan: (code: string) => void,
    private readonly minLength = WEDGE_MIN_LENGTH,
    private readonly maxGapMs = WEDGE_MAX_GAP_MS,
  ) {}

  /**
   * Feed one key (``KeyboardEvent.key``) with its time in milliseconds. True if the key
   * finished a scan, so the caller can keep it from doing anything else.
   */
  feed(key: string, time: number): boolean {
    const gap = time - this.last;
    this.last = time;
    if (key === "Enter") {
      const code = this.buffer;
      this.buffer = "";
      if (code.length >= this.minLength && gap <= this.maxGapMs) {
        this.onScan(code);
        return true;
      }
      return false;
    }
    if (key.length !== 1) {
      return false;
    }
    // A pause means a person is typing: start over with this key.
    this.buffer = gap <= this.maxGapMs ? this.buffer + key : key;
    return false;
  }
}

/** Lets a code through once per window, so a camera held on a label scans it once. */
export class RepeatFilter {
  private readonly seen = new Map<string, number>();

  constructor(private readonly windowMs = REPEAT_WINDOW_MS) {}

  accept(code: string, time: number): boolean {
    const previous = this.seen.get(code);
    this.seen.set(code, time);
    for (const [other, at] of this.seen) {
      if (time - at > this.windowMs) {
        this.seen.delete(other);
      }
    }
    return previous === undefined || time - previous > this.windowMs;
  }
}

/** How long an EAN seen alone waits for the unit's own code to show up beside it. */
export const ARTICLE_HOLD_MS = 400;

/**
 * Chooses what the camera read. A unit label carries two codes: the article's EAN-13
 * (for the till) and the unit's own Code 128. Both are usually in the picture, and the
 * unit's code is the one that names this very piece, so it wins. An EAN counts only
 * when it stays alone for a moment, and not right after a unit's label was read.
 */
export class LabelPicker {
  private held: { code: string; since: number } | null = null;
  private labelSeenAt = Number.NEGATIVE_INFINITY;

  constructor(
    private readonly onPick: (code: string) => void,
    private readonly holdMs = ARTICLE_HOLD_MS,
    private readonly windowMs = REPEAT_WINDOW_MS,
  ) {}

  /** Feed the codes found in one camera frame (possibly none) with the frame's time. */
  frame(codes: readonly string[], time: number): void {
    const own = codes.filter((code) => !isValidEan13(code.trim()));
    if (own.length > 0) {
      this.held = null;
      this.labelSeenAt = time;
      own.forEach((code) => this.onPick(code));
      return;
    }
    const article = codes[0];
    if (article !== undefined && time - this.labelSeenAt > this.windowMs) {
      this.held ??= { code: article, since: time };
    }
    if (this.held !== null && time - this.held.since >= this.holdMs) {
      const { code } = this.held;
      this.held = null;
      this.onPick(code);
    }
  }
}
