import { Geist, Geist_Mono } from "next/font/google";

// Self-hosted by next/font at build time: no request to Google from the visitor's browser.

/** Everything: large and thin in headings, regular in text (see globals.css). */
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
