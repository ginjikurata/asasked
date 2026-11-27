import type { MetadataRoute } from "next";

import { LAUNCHED, ORIGIN } from "@/lib/site";

export const dynamic = "force-static";


export default function robots(): MetadataRoute.Robots {
  return {
    rules: LAUNCHED ? { userAgent: "*", allow: "/", disallow: ["/api/", "/account"] } : { userAgent: "*", disallow: "/" },
    sitemap: `${ORIGIN}/sitemap.xml`,
  };
}
