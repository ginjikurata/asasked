import type { MetadataRoute } from "next";
import { MERCHANTS } from "@/lib/merchants";
import { slug } from "@/lib/catalog";
import { ORIGIN } from "@/lib/site";

export const dynamic = "force-static";

export default function sitemap(): MetadataRoute.Sitemap {
  // /search and /chat are tools with no content of their own, so they are left out.
  const pages = ["", "/stores", "/gift-cards", "/coming", "/demo"];
  // A store page changes when the store is checked again; the lists change with the newest check.
  const newest = MERCHANTS.map((m) => m.checked).filter((d): d is string => !!d).sort().at(-1);
  return [
    ...pages.map((p) => ({ url: `${ORIGIN}${p}`, ...(newest && { lastModified: newest }) })),
    ...MERCHANTS.map((m) => ({ url: `${ORIGIN}/stores/${slug(m.domain)}`, ...(m.checked && { lastModified: m.checked }) })),
  ];
}
