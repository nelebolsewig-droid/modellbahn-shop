"use client";

import { AdminShell } from "@/components/admin/admin-shell";

import { ProductEditor } from "./product-editor";

export function ProductEditorPage({ productId }: { productId: string }) {
  return (
    <AdminShell>
      {({ revalidate }) => <ProductEditor productId={productId} onStreamClosed={revalidate} />}
    </AdminShell>
  );
}
