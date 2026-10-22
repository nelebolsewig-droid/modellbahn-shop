import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { SHOP_NAME } from "@/lib/config";
import { cn } from "@/lib/utils";

import { displayFont, monoFont, sansFont } from "./fonts";
import { Providers } from "./providers";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: SHOP_NAME, template: `%s · ${SHOP_NAME}` },
  description: "3D-gedruckte Modellbahn-Artikel aus der eigenen Werkstatt.",
  applicationName: SHOP_NAME,
};

export const viewport: Viewport = {
  colorScheme: "light dark",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#e8e7de" },
    { media: "(prefers-color-scheme: dark)", color: "#151a18" },
  ],
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="de" className={cn(displayFont.variable, sansFont.variable, monoFont.variable)}>
      <body className="min-h-dvh">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
