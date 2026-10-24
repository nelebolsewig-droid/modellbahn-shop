import type { Route } from "next";
import Link from "next/link";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

type TextLinkProps = Omit<ComponentProps<"a">, "href"> & { href: Route };

/** A link inside running text: Prussian blue, underlined. */
export function TextLink({ href, className, ...props }: TextLinkProps) {
  return (
    <Link
      href={href}
      className={cn(
        "rounded-xs text-accent underline decoration-1 underline-offset-4",
        "transition-colors hover:text-accent-hover",
        className,
      )}
      {...props}
    />
  );
}
