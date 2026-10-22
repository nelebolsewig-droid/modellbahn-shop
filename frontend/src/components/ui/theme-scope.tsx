"use client";

import { createContext, use, type ReactNode } from "react";

import { cn } from "@/lib/utils";

/** Colour themes besides the shop's default (see [data-theme] in globals.css). */
export type Theme = "stellwerk";

const ThemeContext = createContext<Theme | undefined>(undefined);

type ThemeScopeProps = {
  theme: Theme;
  className?: string;
  children: ReactNode;
};

/**
 * Switches the design tokens for everything inside. Content rendered into a portal
 * (dialogs) leaves this element in the DOM, so it reads the theme from the context
 * via {@link useTheme} and sets it again.
 */
export function ThemeScope({ theme, className, children }: ThemeScopeProps) {
  return (
    <ThemeContext value={theme}>
      <div data-theme={theme} className={cn("bg-surface text-ink", className)}>
        {children}
      </div>
    </ThemeContext>
  );
}

export function useTheme(): Theme | undefined {
  return use(ThemeContext);
}
