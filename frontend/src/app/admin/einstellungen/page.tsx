import type { Metadata } from "next";

import { SettingsPage } from "@/components/admin/settings/settings-page";

export const metadata: Metadata = { title: "Einstellungen" };

export default function AdminSettingsPage() {
  return <SettingsPage />;
}
