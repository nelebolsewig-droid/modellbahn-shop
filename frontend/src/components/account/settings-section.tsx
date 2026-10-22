import { useId, type ReactNode } from "react";

import { cn } from "@/lib/utils";

type SettingsSectionProps = {
  title: string;
  description?: ReactNode;
  tone?: "default" | "danger";
  children: ReactNode;
};

/** One titled block on "Mein Konto". */
export function SettingsSection({ title, description, tone = "default", children }: SettingsSectionProps) {
  const headingId = useId();
  return (
    <section
      aria-labelledby={headingId}
      className={cn(
        "rule rounded-md p-6 sm:p-8",
        tone === "danger" ? "border-danger" : "border-line-strong bg-surface-raised",
      )}
    >
      <h2 id={headingId} className="text-3xl">
        {title}
      </h2>
      {description ? <div className="mt-2 max-w-prose text-sm leading-6 text-ink-muted">{description}</div> : null}
      <div className="mt-6">{children}</div>
    </section>
  );
}
