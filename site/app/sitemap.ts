import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/content";

// Every public page; robots.ts points here once the site is launched.
const PAGES = ["", "/spec", "/docs", "/dataset", "/changelog", "/about", "/legal", "/privacy"];

export default function sitemap(): MetadataRoute.Sitemap {
  return PAGES.map((path) => ({ url: `${SITE_URL}${path}` }));
}
