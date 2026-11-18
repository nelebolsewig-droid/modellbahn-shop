import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { SHOP_NAME } from "@/lib/config";
import { cn } from "@/lib/utils";

import { displayFont, monoFont, sansFont, wordmarkSansFont, wordmarkSerifFont } from "./fonts";
import { Providers } from "./providers";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: SHOP_NAME, template: `%s · ${SHOP_NAME}` },
  description: "Fahrzeugmodelle in Handarbeit und Kleinserie: Lkw, Autokrane und Schienenfahrzeuge für Sammler und Modellbahner.",
  applicationName: SHOP_NAME,
};

// One light theme (docs/KONZEPT.md §11); the browser chrome takes the canvas colour.
export const viewport: Viewport = {
  colorScheme: "light",
  themeColor: "#faf6f0",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="de" className={cn(sansFont.variable, monoFont.variable, displayFont.variable, wordmarkSerifFont.variable, wordmarkSansFont.variable)}>
      <body className="min-h-dvh">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
