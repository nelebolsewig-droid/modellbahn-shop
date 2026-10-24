import Link from "next/link";

import { PageHeading } from "@/components/site/page-heading";
import { Button } from "@/components/ui/button";

export default function ProductNotFound() {
  return (
    <div className="mx-auto max-w-6xl px-5 py-16 sm:px-8 lg:py-24">
      <PageHeading caption="Katalog · Ausgemustert" title="Dieses Modell gibt es nicht (mehr)">
        <p>Vielleicht ist der Link veraltet, oder das Modell ist nicht mehr im Programm.</p>
      </PageHeading>
      <Button asChild className="mt-8">
        <Link href="/katalog">Zum Katalog</Link>
      </Button>
    </div>
  );
}
