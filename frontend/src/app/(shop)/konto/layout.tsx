import type { Metadata } from "next";
import type { ReactNode } from "react";

// Account pages are personal or one-off steps; search engines have no business there.
export const metadata: Metadata = {
  robots: { index: false, follow: false },
};

export default function AccountLayout({ children }: { children: ReactNode }) {
  return children;
}
