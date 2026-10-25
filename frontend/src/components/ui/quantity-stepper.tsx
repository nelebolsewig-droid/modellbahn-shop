"use client";

import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

type QuantityStepperProps = {
  value: number;
  onChange: (value: number) => void;
  /** What is counted, for screen readers: "Menge", "Menge Stellwerk Altenau". */
  label: string;
  min?: number;
  max?: number;
  disabled?: boolean;
  className?: string;
};

/**
 * A quantity as minus, number, plus in one pill. The number is announced when it
 * changes; the buttons say what they do and stop at the limits.
 */
export function QuantityStepper({
  value,
  onChange,
  label,
  min = 1,
  max = 99,
  disabled = false,
  className,
}: QuantityStepperProps) {
  const step = (delta: number) => {
    const next = Math.min(max, Math.max(min, value + delta));
    if (next !== value) {
      onChange(next);
    }
  };
  return (
    <div
      role="group"
      aria-label={label}
      className={cn(
        "inline-flex h-10 items-center rounded-full border border-line-control bg-surface",
        disabled && "opacity-60",
        className,
      )}
    >
      <StepButton label="Eins weniger" disabled={disabled || value <= min} onClick={() => step(-1)}>
        <path d="M5 10h10" />
      </StepButton>
      <output aria-live="polite" className="w-8 text-center text-sm font-medium tabular-nums">
        {value}
      </output>
      <StepButton label="Eins mehr" disabled={disabled || value >= max} onClick={() => step(1)}>
        <path d="M5 10h10M10 5v10" />
      </StepButton>
    </div>
  );
}

function StepButton({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "grid size-10 cursor-pointer place-items-center rounded-full text-ink",
        "hover:bg-sunken disabled:cursor-not-allowed disabled:text-ink-disabled disabled:hover:bg-transparent",
      )}
    >
      <svg viewBox="0 0 20 20" className="size-4" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
        {children}
      </svg>
    </button>
  );
}
