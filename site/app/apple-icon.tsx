import { ImageResponse } from "next/og";
import { MarkImage } from "@/components/MarkImage";

// Home-screen icon for iOS: the mark on the dark tile, like app/icon.svg.
export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", background: "#0b0b0b" }}>
        <MarkImage cell={22} ink="#f1f1ee" signal="#ff5a3c" />
      </div>
    ),
    size,
  );
}
