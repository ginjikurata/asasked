import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono, Inter_Tight } from "next/font/google";
import { Footer, Header } from "@/components/Chrome";
import { PixelField } from "@/components/PixelField";
import { LAUNCHED, SITE_URL } from "@/lib/content";
import { DESCRIPTION, HEADLINE, TITLE } from "@/lib/headline";
import "./globals.css";

const interTight = Inter_Tight({
  variable: "--font-inter-tight",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const plexMono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: TITLE, template: "%s · AsAsked" },
  description: DESCRIPTION,
  applicationName: "AsAsked",
  // indexed only once launched (LAUNCHED in lib/content.ts)
  robots: LAUNCHED ? undefined : { index: false, follow: false },
  openGraph: { type: "website", siteName: "AsAsked", url: SITE_URL, title: HEADLINE, description: DESCRIPTION },
  twitter: { card: "summary_large_image", title: HEADLINE, description: DESCRIPTION },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#0b0b0b" },
  ],
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${interTight.variable} ${plexMono.variable}`}>
      <body>
        <PixelField />
        <Header />
        {children}
        <Footer />
      </body>
    </html>
  );
}
