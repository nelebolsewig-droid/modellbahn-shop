"use client";

import Link from "next/link";
import type { ComponentProps } from "react";

import { decalsPath } from "@/lib/catalog/decals";
import { useLastScale } from "@/lib/catalog/last-scale";

/** A link to the decals, in the scale browsed last if there is one. */
export function DecalsLink(props: Omit<ComponentProps<typeof Link>, "href">) {
  return <Link href={decalsPath(useLastScale()?.code)} {...props} />;
}
