import type { Metadata } from "next";

import { HelpPage } from "@/components/admin/help/help-page";

export const metadata: Metadata = { title: "Hilfe" };

export default function AdminHelpPage() {
  return <HelpPage />;
}
