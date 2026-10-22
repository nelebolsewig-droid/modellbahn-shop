import { Barlow_Condensed, IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";

// Self-hosted by next/font at build time: no request to Google from the visitor's browser.

/** Headings: condensed, uppercase, slightly spaced (see h1–h3 in globals.css). */
export const displayFont = Barlow_Condensed({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-barlow-condensed",
  display: "swap",
});

/** Body text; a variable font, so every weight comes from one file. */
export const sansFont = IBM_Plex_Sans({
  subsets: ["latin"],
  variable: "--font-plex-sans",
  display: "swap",
});

/** Codes, numbers, timestamps and the small caption labels. */
export const monoFont = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-plex-mono",
  display: "swap",
});
