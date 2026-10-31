import { ImageResponse } from "next/og";
import { MarkImage } from "@/components/MarkImage";
import { HEADLINE, TAGLINE, TITLE } from "@/lib/headline";

// The picture link previews show (Slack, X, LinkedIn, messengers).
export const alt = TITLE;
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

// Inter Tight, as on the site. Cached, so the image is rendered once at build time instead of on
// every request; if Google Fonts is unreachable the image still builds, in the default font.
const FONTS = [
  { weight: 400, url: "https://fonts.gstatic.com/s/intertight/v9/NGSnv5HMAFg6IuGlBNMjxJEL2VmU3NS7Z2mjDw-qXA.ttf" },
  { weight: 700, url: "https://fonts.gstatic.com/s/intertight/v9/NGSnv5HMAFg6IuGlBNMjxJEL2VmU3NS7Z2mj6AiqXA.ttf" },
] as const;

async function loadFonts() {
  "use cache";
  try {
    return await Promise.all(
      FONTS.map(async ({ weight, url }) => {
        const r = await fetch(url);
        if (!r.ok) throw new Error(`${url}: ${r.status}`);
        return { name: "Inter Tight", data: await r.arrayBuffer(), weight, style: "normal" as const };
      }),
    );
  } catch {
    return undefined;
  }
}

export default async function OpengraphImage() {
  const fonts = await loadFonts();
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", justifyContent: "space-between", padding: 80, background: "#0b0b0b", color: "#f1f1ee", fontFamily: "Inter Tight" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
          <MarkImage cell={12} ink="#f1f1ee" signal="#ff5a3c" />
          <div style={{ fontSize: 44, fontWeight: 700, letterSpacing: -1 }}>AsAsked</div>
        </div>
        <div style={{ fontSize: 76, fontWeight: 700, lineHeight: 1.05, letterSpacing: -2.5 }}>{HEADLINE}</div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 30, color: "#a8a8a2" }}>
          <div>{TAGLINE}</div>
          <div>asasked.dev</div>
        </div>
      </div>
    ),
    { ...size, fonts },
  );
}
