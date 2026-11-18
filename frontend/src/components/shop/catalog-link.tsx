"use client";

import Link from "next/link";
import type { ComponentProps } from "react";

import { useCatalogHref } from "@/lib/catalog/last-scale";

/** A link to the catalogue that opens the scale browsed last, if there is one. */
export function CatalogLink(props: Omit<ComponentProps<typeof Link>, "href">) {
  return <Link href={useCatalogHref()} {...props} />;
}
