import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono, Inter_Tight } from "next/font/google";
import { Footer, Header } from "@/components/Chrome";
import { PixelField } from "@/components/PixelField";
import { LAUNCHED, SITE_URL } from "@/lib/content";
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

const description =
  "A pre-checkout guard for AI shopping agents: before payment, it checks the cart against what the person " +
  "actually asked for and answers proceed or ask. Open library, sandbox store, benchmark and spec.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: "AsAsked — did the agent buy what you asked for?", template: "%s · AsAsked" },
  description,
  // until launch no page is indexed: the product is not public yet
  robots: LAUNCHED ? undefined : { index: false, follow: false },
  openGraph: { type: "website", url: SITE_URL, title: "AsAsked", description },
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
