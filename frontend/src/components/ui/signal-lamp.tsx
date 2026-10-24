import { cn } from "@/lib/utils";

export type LampColor = "green" | "yellow" | "red" | "blue" | "off";

// A flat dot with a faint halo of its own colour.
const LAMP_CLASSES: Record<LampColor, string> = {
  green: "bg-success shadow-[0_0_0_4px_var(--success-subtle)]",
  yellow: "bg-warning shadow-[0_0_0_4px_var(--warning-subtle)]",
  red: "bg-danger shadow-[0_0_0_4px_var(--danger-subtle)]",
  blue: "bg-accent shadow-[0_0_0_4px_var(--accent-subtle)]",
  off: "bg-line-strong",
};

type SignalLampProps = {
  color: LampColor;
  /** Blinks, e.g. while a connection is being re-established. */
  blinking?: boolean;
  className?: string;
};

/**
 * A status lamp. Decorative only: the state must always be written out next to it
 * as text, colour alone carries no information.
 */
export function SignalLamp({ color, blinking = false, className }: SignalLampProps) {
  return (
    <span aria-hidden="true" className={cn("inline-flex size-4 shrink-0 items-center justify-center", className)}>
      <span className={cn("size-2 rounded-full", LAMP_CLASSES[color], blinking && "animate-lamp-pulse")} />
    </span>
  );
}
