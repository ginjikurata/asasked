import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono, Inter_Tight } from "next/font/google";
import { WalletButton } from "@/components/WalletButton";
import { MARK_END, MARK_PATH } from "@/lib/mark";
import { LAUNCHED } from "@/lib/site";
import "./globals.css";

const interTight = Inter_Tight({ variable: "--font-inter-tight", subsets: ["latin"], weight: ["400", "500", "600", "700"] });
const plexMono = IBM_Plex_Mono({ variable: "--font-plex-mono", subsets: ["latin"], weight: ["400", "500"] });


export const metadata: Metadata = {
  metadataBase: new URL("https://lab.asasked.dev"),
  title: { default: "Shops that take crypto · AsAsked Lab", template: "%s · AsAsked Lab" },
  description:
    "Online stores where we found signs they take crypto, each checked one by one, with products to buy. You pay the store directly; we never hold your money.",
  robots: LAUNCHED ? undefined : { index: false, follow: false },
  alternates: { canonical: "./" },
  openGraph: {
    type: "website",
    siteName: "AsAsked Lab",
    title: "Shops that take crypto · AsAsked Lab",
    description: "Online stores where we found signs they take crypto, checked one by one. You pay the store directly.",
    url: "./",
    images: [{ url: "/og.png", width: 1200, height: 630, alt: "AsAsked Lab: shops that take crypto" }],
  },
  twitter: { card: "summary_large_image", images: ["/og.png"], title: "Shops that take crypto · AsAsked Lab", description: "Online stores where we found signs they take crypto, checked one by one." },
};

// Who runs the site, for search engines (schema.org).
const JSON_LD = {
  "@context": "https://schema.org",
  "@graph": [
    { "@type": "Organization", "@id": "https://asasked.dev/#org", name: "AsAsked", url: "https://asasked.dev" },
    {
      "@type": "WebSite",
      "@id": "https://lab.asasked.dev/#site",
      name: "AsAsked Lab",
      url: "https://lab.asasked.dev",
      publisher: { "@id": "https://asasked.dev/#org" },
    },
  ],
};

export const viewport: Viewport = {
  themeColor: "#faf8f4",
  colorScheme: "light",
};

function Mark() {
  return (
    <svg viewBox="0 0 6 4" className="h-4 w-6" aria-hidden shapeRendering="crispEdges">
      {MARK_PATH.map(([x, y]) => (
        <rect key={`${x}${y}`} x={x} y={y} width="1" height="1" className="fill-ink" />
      ))}
      <rect x={MARK_END[0]} y={MARK_END[1]} width="1" height="1" className="fill-signal" />
    </svg>
  );
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${interTight.variable} ${plexMono.variable}`}>
      <body>
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(JSON_LD) }} />
        <a
          href="#content"
          className="sr-only rounded-full bg-ink px-4 py-2.5 text-sm font-medium text-paper focus:not-sr-only focus:fixed focus:left-3 focus:top-2 focus:z-30"
        >
          Skip to content
        </a>
        <header className="sticky top-0 z-20 border-b border-line bg-paper/85 backdrop-blur">
          <div className="flex h-12 items-center justify-between gap-2 px-[var(--gutter)] sm:gap-6">
            <a href="/" className="flex items-center gap-2 text-[17px] font-semibold tracking-tight">
              <Mark />
              AsAsked <span className="font-normal text-muted max-[429px]:hidden">Lab</span>
            </a>
            <a
              href="/coming"
              title="What's coming next"
              className="relative mr-auto rounded-full border border-signal/30 bg-signal-soft px-1.5 py-0.5 font-mono text-[11px] uppercase tracking-wider text-signal-ink after:absolute after:-inset-y-3 after:inset-x-0 hover:border-signal max-[399px]:hidden sm:-ml-4 sm:px-2"
            >
              Beta
            </a>
            <nav aria-label="Main" className="flex items-center gap-2 whitespace-nowrap text-[13px] sm:gap-6 sm:text-sm">
              <a href="/stores" className="py-3 hover:underline">
                Stores
              </a>
              <a href="/search" className="py-3 hover:underline">
                Products
              </a>
              <a href="/chat" className="py-3 hover:underline">
                Chat
              </a>
              <a href="/gift-cards" className="py-3 hover:underline max-[349px]:hidden">
                <span className="sm:hidden">Gifts</span>
                <span className="hidden sm:inline">Gift cards</span>
              </a>
              <a href="https://asasked.dev" className="link hidden text-muted lg:inline">
                asasked.dev
              </a>
              <WalletButton />
            </nav>
          </div>
        </header>
        <div id="content" tabIndex={-1} className="outline-none">
          {children}
        </div>
        <footer className="mt-32 border-t border-line">
          <div className="wide flex flex-col gap-3 py-10 text-sm text-muted">
            <nav className="flex flex-wrap gap-x-5 text-ink" aria-label="Site">
              <a href="/stores" className="py-2 hover:underline">Stores</a>
              <a href="/search" className="py-2 hover:underline">Products</a>
              <a href="/chat" className="py-2 hover:underline">Chat</a>
              <a href="/gift-cards" className="py-2 hover:underline">Gift cards</a>
              <a href="/account" className="py-2 hover:underline">Account</a>
              <a href="/coming" className="py-2 hover:underline">What&apos;s coming</a>
            </nav>
            <p>
              An experiment by{" "}
              <a href="https://asasked.dev" className="link text-ink">
                AsAsked
              </a>
              , made by{" "}
              <a href="https://concord.solutions" className="link text-ink">
                Concord
              </a>
              . Store names and trademarks belong to their owners; a listing here is not an endorsement.
            </p>
            <p>
              This is a beta.{" "}
              <a href="/coming" className="link text-ink">
                See what&apos;s coming
              </a>{" "}
              or{" "}
              <a href="/demo" className="link text-ink">
                watch the agent demo
              </a>
              .
            </p>
            <p>
              No ads, no trackers, no email or password. Search on the Products page happens in your browser, and your search
              history stays there. Chat messages go to our server and to an AI model to get an answer; we do not save them. If
              you open an{" "}
              <a href="/account" className="link text-ink">
                account
              </a>{" "}
              with your wallet, we keep your wallet address, the sizes and budget you save and the carts your agent saves, with
              one cookie that keeps you signed in. A delivery address, if you add one, is locked with your wallet before it
              leaves your browser, and we cannot read it. You can delete all of it from the account page.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
