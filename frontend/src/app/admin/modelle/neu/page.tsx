import type { Metadata } from "next";

import { AdminShell } from "@/components/admin/admin-shell";
import { ModelWizard } from "@/components/admin/catalog/model-wizard";

export const metadata: Metadata = { title: "Neues Modell" };

/** A new model in four steps, made for the phone at the crates (ADR 0028). */
export default function AdminNewModelPage() {
  return (
    <AdminShell>
      <ModelWizard />
    </AdminShell>
  );
}
