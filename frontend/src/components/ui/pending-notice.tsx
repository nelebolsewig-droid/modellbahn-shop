import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

import { SignalLamp } from "./signal-lamp";

/** "Something is on its way": a blinking yellow lamp and the text, announced politely. */
export function PendingNotice({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div role="status" className={cn("flex items-center gap-3 text-ink-muted", className)}>
      <SignalLamp color="yellow" blinking />
      <span>{children}</span>
    </div>
  );
}
