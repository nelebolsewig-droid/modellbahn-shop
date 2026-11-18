import { Arimo, Bricolage_Grotesque, Geist, Geist_Mono, Tinos } from "next/font/google";

// Self-hosted by next/font at build time: no request to Google from the visitor's browser.

/** Running text and controls. */
export const sansFont = Geist({
  subsets: ["latin"],
  variable: "--font-geist",
  display: "swap",
});

/** Values that are read or typed: EAN, part numbers, dimensions, event types. */
export const monoFont = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-geist-mono",
  display: "swap",
});

/** Headings: heavy and tight (see globals.css, ADR 0030). */
export const displayFont = Bricolage_Grotesque({
  subsets: ["latin"],
  variable: "--font-bricolage",
  display: "swap",
});

// The wordmark is set in Times New Roman bold italic and Arial bold. Devices without
// these two (Android, Linux) get the metric-compatible Tinos and Arimo instead.
export const wordmarkSerifFont = Tinos({
  subsets: ["latin"],
  weight: "700",
  style: "italic",
  variable: "--font-tinos",
  display: "swap",
  preload: false,
});

export const wordmarkSansFont = Arimo({
  subsets: ["latin"],
  weight: "700",
  variable: "--font-arimo",
  display: "swap",
  preload: false,
});
