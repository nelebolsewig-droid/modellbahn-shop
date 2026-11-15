import type { Metadata } from "next";

import { LeadTimeSettingsPage } from "@/components/admin/settings/lead-time-settings";

export const metadata: Metadata = { title: "Lieferzeit" };

export default function AdminLeadTimePage() {
  return <LeadTimeSettingsPage />;
}
