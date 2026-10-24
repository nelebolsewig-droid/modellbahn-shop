import type { Metadata } from "next";

import { ProductEditorPage } from "@/components/admin/catalog/product-editor-page";

export const metadata: Metadata = { title: "Produkt bearbeiten" };

export default async function AdminProductPage({ params }: PageProps<"/admin/katalog/[id]">) {
  const { id } = await params;
  return <ProductEditorPage productId={id} />;
}
