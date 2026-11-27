import type { Metadata } from "next";
import { ProductSearch } from "@/components/ProductSearch";

export const metadata: Metadata = {
  title: "Search products",
  description: "Search products from stores that take crypto on their own checkout.",
};

export default function Search() {
  return (
    <main className="wide">
      <ProductSearch />
    </main>
  );
}
