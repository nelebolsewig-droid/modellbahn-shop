import type { ReactNode } from "react";

import { ShopFrame } from "@/components/site/shop-frame";

export default function ShopLayout({ children }: { children: ReactNode }) {
  return <ShopFrame>{children}</ShopFrame>;
}
