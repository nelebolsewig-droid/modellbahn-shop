import type { Route } from "next";
import Link from "next/link";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

type TextLinkProps = Omit<ComponentProps<"a">, "href"> & { href: Route };

/** A link inside running text: underlined in the accent colour. */
export function TextLink({ href, className, ...props }: TextLinkProps) {
  return (
    <Link
      href={href}
      className={cn(
        "rounded-xs font-medium text-ink underline decoration-accent decoration-2 underline-offset-4",
        "transition-colors hover:decoration-ink",
        className,
      )}
      {...props}
    />
  );
}
