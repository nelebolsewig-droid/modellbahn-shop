import { cn } from "@/lib/utils";

export type LampColor = "green" | "yellow" | "red" | "off";

const LAMP_CLASSES: Record<LampColor, string> = {
  green: "bg-lamp-green shadow-[0_0_10px_1px_var(--color-lamp-green)]",
  yellow: "bg-lamp-yellow shadow-[0_0_10px_1px_var(--color-lamp-yellow)]",
  red: "bg-lamp-red shadow-[0_0_10px_1px_var(--color-lamp-red)]",
  off: "bg-lamp-off",
};

type SignalLampProps = {
  color: LampColor;
  /** Blinks, e.g. while a connection is being re-established. */
  blinking?: boolean;
  className?: string;
};

/**
 * A signal lamp in its dark housing. Decorative only: the state must always be
 * written out next to it as text, colour alone carries no information.
 */
export function SignalLamp({ color, blinking = false, className }: SignalLampProps) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "inline-flex size-5 shrink-0 items-center justify-center rounded-full bg-lamp-housing ring-1 ring-line",
        className,
      )}
    >
      <span
        className={cn(
          "size-2.5 rounded-full",
          LAMP_CLASSES[color],
          blinking && "animate-lamp-pulse",
        )}
      />
    </span>
  );
}
