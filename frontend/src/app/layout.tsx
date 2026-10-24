import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { SHOP_NAME } from "@/lib/config";
import { cn } from "@/lib/utils";

import { monoFont, sansFont } from "./fonts";
import { Providers } from "./providers";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: SHOP_NAME, template: `%s · ${SHOP_NAME}` },
  description: "3D-gedruckte Modellbahn-Artikel aus der eigenen Werkstatt.",
  applicationName: SHOP_NAME,
};

// One light theme (docs/KONZEPT.md §11); the browser chrome takes the canvas colour.
export const viewport: Viewport = {
  colorScheme: "light",
  themeColor: "#f4f4f1",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="de" className={cn(sansFont.variable, monoFont.variable)}>
      <body className="min-h-dvh">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
