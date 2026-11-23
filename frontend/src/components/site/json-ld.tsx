import { serializeJsonLd } from "@/lib/site/structured-data";

/** schema.org data for search engines (ADR 0047); invisible on the page. */
export function JsonLd({ data }: { data: Record<string, unknown> }) {
  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: serializeJsonLd(data) }} />;
}
