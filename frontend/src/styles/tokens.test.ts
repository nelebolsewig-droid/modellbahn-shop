// @vitest-environment node

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

/**
 * Every text colour must stay legible on the grounds it is used on (WCAG 2.2: 4.5:1
 * for text, 3:1 for control borders and the focus ring). A colour change in
 * tokens.css that breaks a pair fails here, before anyone sees it.
 */

const css = readFileSync(new URL("./tokens.css", import.meta.url), "utf8");

const declarations = new Map(
  [...css.matchAll(/--([\w-]+):\s*([^;]+);/g)].map((match) => [match[1] ?? "", (match[2] ?? "").trim()]),
);

function hex(token: string, seen: string[] = []): string {
  const value = declarations.get(token);
  if (value === undefined) {
    throw new Error(`--${token} is not declared`);
  }
  const alias = /^var\(--([\w-]+)\)$/.exec(value);
  if (alias?.[1]) {
    if (seen.includes(alias[1])) {
      throw new Error(`alias cycle: ${[...seen, alias[1]].join(" → ")}`);
    }
    return hex(alias[1], [...seen, token]);
  }
  if (!/^#[0-9a-f]{6}$/i.test(value)) {
    throw new Error(`--${token} is not a six-digit hex colour: ${value}`);
  }
  return value;
}

function luminance(colour: string): number {
  const channels = [1, 3, 5].map((start) => Number.parseInt(colour.slice(start, start + 2), 16) / 255);
  const [r = 0, g = 0, b = 0] = channels.map((c) =>
    c <= 0.039_28 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4,
  );
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(foreground: string, background: string): number {
  const [light, dark] = [luminance(hex(foreground)), luminance(hex(background))].sort((a, b) => b - a);
  return ((light ?? 0) + 0.05) / ((dark ?? 0) + 0.05);
}

const GROUNDS = ["canvas", "stage", "surface", "sunken"] as const;

const TEXT_PAIRS: [string, string][] = [
  ...["ink", "ink-secondary", "ink-tertiary", "accent", "danger", "success", "warning"].flatMap(
    (text) => GROUNDS.map((ground): [string, string] => [text, ground]),
  ),
  ["on-selected", "selected"],
  ["on-accent", "accent"],
  ["on-selected", "danger"],
  ["ink", "accent-subtle"],
  ["accent", "accent-subtle"],
  ["ink", "success-subtle"],
  ["success", "success-subtle"],
  ["ink", "warning-subtle"],
  ["warning", "warning-subtle"],
  ["ink", "danger-subtle"],
  ["danger", "danger-subtle"],
  ["drawing-dimension", "stage"],
  ["on-viewfinder", "viewfinder"],
  ["on-viewfinder-muted", "viewfinder"],
];

const MARK_PAIRS: [string, string][] = [
  ...GROUNDS.flatMap((ground): [string, string][] => [
    ["focus", ground],
    ["line-control", ground === "sunken" ? "surface" : ground],
    ["selected", ground],
  ]),
];

describe("design tokens", () => {
  it.each(TEXT_PAIRS)("%s on %s is legible text (4.5:1)", (text, ground) => {
    expect(contrast(text, ground)).toBeGreaterThanOrEqual(4.5);
  });

  it.each(MARK_PAIRS)("%s on %s is a visible mark (3:1)", (mark, ground) => {
    expect(contrast(mark, ground)).toBeGreaterThanOrEqual(3);
  });

  it("has no pure black and no dark ground", () => {
    expect(hex("ink")).not.toBe("#000000");
    for (const ground of GROUNDS) {
      expect(luminance(hex(ground))).toBeGreaterThan(0.8);
    }
  });
});
