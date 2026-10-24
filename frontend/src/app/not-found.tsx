import type { Metadata } from "next";
import Link from "next/link";

import { PageHeading } from "@/components/site/page-heading";
import { ShopFrame } from "@/components/site/shop-frame";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = {
  title: "Seite nicht gefunden",
};

export default function NotFound() {
  return (
    <ShopFrame>
      <div className="mx-auto max-w-6xl px-5 py-16 sm:px-8 lg:py-24">
        <PageHeading caption="Fehler 404 · Kein Anschluss" title="Diese Seite gibt es nicht">
          <p>
            Vielleicht ist der Link veraltet oder hat einen Tippfehler. Von der Startseite aus
            findest du weiter.
          </p>
        </PageHeading>
        <Button asChild className="mt-8">
          <Link href="/">Zur Startseite</Link>
        </Button>
      </div>
    </ShopFrame>
  );
}
