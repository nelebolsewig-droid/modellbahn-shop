import { cn } from "@/lib/utils";

export type StatusTone = "neutral" | "success" | "warning" | "danger" | "accent";

const DOT: Readonly<Record<StatusTone, string>> = {
  neutral: "bg-ink-tertiary",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  accent: "bg-accent",
};

const TEXT: Readonly<Record<StatusTone, string>> = {
  neutral: "text-ink-secondary",
  success: "text-success",
  warning: "text-warning",
  danger: "text-danger",
  accent: "text-accent",
};

type StatusBadgeProps = {
  tone: StatusTone;
  children: string;
  /** A pulsing dot for states that are still moving (uploading, processing). */
  busy?: boolean;
  className?: string;
};

/** A state as dot plus word, never as colour alone: „● Im Shop“, „● Wird verarbeitet“. */
export function StatusBadge({ tone, children, busy = false, className }: StatusBadgeProps) {
  return (
    <span className={cn("inline-flex items-center gap-2 text-hint font-medium", TEXT[tone], className)}>
      <span
        aria-hidden="true"
        className={cn("size-2 shrink-0 rounded-full", DOT[tone], busy && "animate-lamp-pulse")}
      />
      {children}
    </span>
  );
}
