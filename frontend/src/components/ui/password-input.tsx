"use client";

import { useState, type ComponentProps } from "react";

import { cn } from "@/lib/utils";

import { Input } from "./input";

type PasswordInputProps = Omit<ComponentProps<"input">, "type">;

/** Password field with a button that shows the typed text (instead of a repeat field). */
export function PasswordInput({ className, id, ...props }: PasswordInputProps) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="relative">
      <Input
        id={id}
        type={visible ? "text" : "password"}
        className={cn("pr-28", className)}
        spellCheck={false}
        autoCapitalize="none"
        {...props}
      />
      <button
        type="button"
        onClick={() => setVisible((current) => !current)}
        aria-controls={id}
        aria-label={visible ? "Passwort verbergen" : "Passwort anzeigen"}
        className="label-caps absolute inset-y-1.5 right-1.5 cursor-pointer rounded-full px-3 text-ink-tertiary transition-colors hover:bg-sunken hover:text-ink"
      >
        {visible ? "Verbergen" : "Anzeigen"}
      </button>
    </div>
  );
}
