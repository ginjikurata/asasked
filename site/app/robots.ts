import type { MetadataRoute } from "next";
import { LAUNCHED, SITE_URL } from "@/lib/content";

// Until launch nothing is indexed: the product is not public yet.
export default function robots(): MetadataRoute.Robots {
  if (!LAUNCHED) return { rules: { userAgent: "*", disallow: "/" } };
  return { rules: { userAgent: "*", allow: "/" }, sitemap: `${SITE_URL}/sitemap.xml` };
}
