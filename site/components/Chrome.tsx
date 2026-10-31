import Link from "next/link";
import { CONCORD_URL, GITHUB_URL, NAV, PYPI_URL, RELEASE_URL, STATUS, VERSION, VI_URL } from "@/lib/content";

/** Link into the public repository. */
export function GitHubLink({ path = "", children }: { path?: string; children: React.ReactNode }) {
  return (
    <a href={`${GITHUB_URL}${path}`} className="link">
      {children}
    </a>
  );
}

/** A tiny pixel mark: a cart's path ending in one red pixel. */
function Mark() {
  const px = [
    [0, 0], [0, 1], [0, 2], [1, 2], [2, 2], [3, 2], [3, 1], [4, 1],
  ];
  return (
    <svg viewBox="0 0 6 4" className="h-4 w-6" aria-hidden shapeRendering="crispEdges">
      {px.map(([x, y]) => (
        <rect key={`${x}${y}`} x={x} y={y} width="1" height="1" className="fill-ink" />
      ))}
      <rect x="5" y="0" width="1" height="1" className="fill-signal" />
    </svg>
  );
}

export function Header() {
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-paper/85 backdrop-blur">
      <div className="flex h-12 items-center justify-between gap-6 px-[var(--gutter)]">
        <div className="flex min-w-0 items-center gap-5">
          <Link href="/" className="flex items-center gap-2 text-[17px] font-semibold tracking-tight">
            <Mark />
            AsAsked
          </Link>
          <span className="meta hidden truncate md:inline">
            <span className="text-pass">●</span> {STATUS}
          </span>
        </div>
        <nav aria-label="Sections" className="hidden shrink-0 items-center gap-6 whitespace-nowrap text-sm lg:flex">
          {NAV.map((item) => (
            <Link key={item.href} href={item.href} className="text-muted hover:text-ink">
              {item.label}
            </Link>
          ))}
          <GitHubLink>GitHub</GitHubLink>
          <a href={PYPI_URL} className="link">
            PyPI
          </a>
        </nav>
      </div>
    </header>
  );
}

export function Footer() {
  return (
    <footer className="mt-32 border-t border-line bg-paper">
      <div className="column flex flex-col gap-3 py-10 text-sm text-muted">
        <nav aria-label="Pages" className="mb-3 flex flex-wrap gap-x-6 gap-y-2 text-ink">
          {NAV.map((item) => (
            <Link key={item.href} href={item.href} className="link">
              {item.label}
            </Link>
          ))}
        </nav>
        <p>
          Made by{" "}
          <a href={CONCORD_URL} className="link text-ink">
            Concord
          </a>
          . Open source, Apache-2.0:{" "}
          <GitHubLink>code on GitHub</GitHubLink>,{" "}
          <a href={PYPI_URL} className="link">
            <code className="font-mono">pip install asasked</code>
          </a>
          , latest release{" "}
          <a href={RELEASE_URL} className="link">
            v{VERSION}
          </a>
          .
        </p>
        <p>
          An independent project built on top of{" "}
          <a href={VI_URL} className="link">
            Verifiable Intent
          </a>
          . Not affiliated with its authors, Mastercard or Google.
        </p>
        <nav aria-label="More" className="flex flex-wrap gap-x-6 gap-y-2">
          <Link href="/changelog" className="link">
            Changelog
          </Link>
          <Link href="/legal" className="link">
            Legal notice
          </Link>
          <Link href="/privacy" className="link">
            Privacy
          </Link>
        </nav>
      </div>
    </footer>
  );
}
