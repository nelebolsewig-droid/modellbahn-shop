import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { DensityScope } from "@/components/ui/density-scope";
import { SHOP_NAME } from "@/lib/config";

export const metadata: Metadata = {
  // `default` still passes through the root layout's template ("%s · <shop name>");
  // `template` replaces it for the pages below /admin.
  title: { default: "Stellwerk", template: `%s · Stellwerk · ${SHOP_NAME}` },
  robots: { index: false, follow: false },
};

// The page reaches the screen's edges, so the phone's bottom bar can sit on the very bottom;
// the bar and the sides keep clear of the rounded corners and the notch themselves.
export const viewport: Viewport = { viewportFit: "cover" };

/** The admin area ("Stellwerk"): the shop's light design, with more compact controls. */
export default function AdminLayout({ children }: { children: ReactNode }) {
  return (
    <DensityScope
      density="werkstatt"
      className="min-h-dvh pr-[env(safe-area-inset-right)] pl-[env(safe-area-inset-left)]"
    >
      {children}
    </DensityScope>
  );
}
