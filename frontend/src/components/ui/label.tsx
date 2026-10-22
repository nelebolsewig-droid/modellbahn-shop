"use client";

import { Root } from "@radix-ui/react-label";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

export function Label({ className, ...props }: ComponentProps<typeof Root>) {
  return (
    <Root
      className={cn("block text-sm leading-5 font-medium text-ink select-none", className)}
      {...props}
    />
  );
}
