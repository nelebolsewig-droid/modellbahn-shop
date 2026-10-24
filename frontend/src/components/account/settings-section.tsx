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
      className="rounded-lg bg-surface p-6 sm:p-8"
    >
      <h2 id={headingId} className={cn("text-heading", tone === "danger" && "text-danger")}>
        {title}
      </h2>
      {description ? <div className="mt-2 max-w-prose text-small text-ink-secondary">{description}</div> : null}
      <div className="mt-6">{children}</div>
    </section>
  );
}
