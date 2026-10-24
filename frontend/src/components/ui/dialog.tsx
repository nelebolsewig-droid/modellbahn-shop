"use client";

import {
  Close,
  Content,
  Description,
  Overlay,
  Portal,
  Root,
  Title,
  Trigger,
} from "@radix-ui/react-dialog";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

import { useDensity } from "./density-scope";

// Radix provides the focus trap, Escape to close, scroll lock, focus return to the
// trigger and the ARIA wiring (role="dialog", aria-modal, labelled by the title).

export const Dialog = Root;
export const DialogTrigger = Trigger;
export const DialogClose = Close;

export function DialogContent({ className, children, ...props }: ComponentProps<typeof Content>) {
  // The portal renders at the end of <body>, outside any DensityScope.
  const density = useDensity();
  return (
    <Portal>
      <Overlay className="fixed inset-0 z-40 bg-scrim backdrop-blur-[2px]" />
      <Content
        data-density={density}
        className={cn(
          "fixed top-1/2 left-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2",
          "max-h-[calc(100dvh-2rem)] overflow-y-auto rounded-lg bg-surface p-8 text-ink shadow-overlay",
          className,
        )}
        {...props}
      >
        {children}
      </Content>
    </Portal>
  );
}

export function DialogTitle({ className, ...props }: ComponentProps<typeof Title>) {
  return <Title className={cn("text-heading", className)} {...props} />;
}

export function DialogDescription({ className, ...props }: ComponentProps<typeof Description>) {
  return <Description className={cn("mt-3 text-small text-ink-secondary", className)} {...props} />;
}
