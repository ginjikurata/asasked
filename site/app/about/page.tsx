import type { Metadata } from "next";
import Link from "next/link";
import { GitHubLink } from "@/components/Chrome";
import { PageHead } from "@/components/PageHead";
import { CONCORD_URL, RESULTS, VI_URL } from "@/lib/content";

export const metadata: Metadata = {
  title: "About",
  description: "Who makes AsAsked, how it relates to Verifiable Intent, and the rules it keeps.",
  alternates: { canonical: "/about" },
};

export default function AboutPage() {
  return (
    <main>
      <PageHead kicker="About" title="An open reference for checking a cart against a request">
        <p className="text-muted">
          AsAsked is a library, a sandbox store, a benchmark and a spec for one question: before an AI agent pays,
          does the cart match what the person asked for?
        </p>
      </PageHead>

      <article className="doc column">
        <h2 id="who"><a href="#who">Who makes it</a></h2>
        <p>
          AsAsked is made by{" "}
          <a href={CONCORD_URL}>Concord</a>, a product studio. It is open source under Apache-2.0: the guard, the
          store, the harness and the open half of the dataset. For anything else, reach us through{" "}
          <a href={`${CONCORD_URL}/contact`}>Concord</a>.
        </p>

        <h2 id="vi"><a href="#vi">Verifiable Intent</a></h2>
        <p>
          AsAsked works on top of <a href={VI_URL}>Verifiable Intent</a>, an open draft standard for cryptographic
          agent authorization in commerce, and does not modify it. It is an independent project: not affiliated with
          the standard&apos;s authors, Mastercard or Google, and not endorsed by them. We use the reference SDK as
          published, under its Apache-2.0 licence.
        </p>

        <h2 id="rules"><a href="#rules">The rules we keep</a></h2>
        <ul>
          <li>
            <strong>Every number can be checked.</strong> Figures on this site come from the repository and its
            runs; the examples are real output of the sandbox and the guard.
          </li>
          <li>
            <strong>The decision is code, not a model.</strong> A model only turns words into facts. Whether a cart
            matches is decided by plain deterministic code, so every <code>ask</code> can be checked by hand.
          </li>
          <li>
            <strong>Costs are counted with benefits.</strong> The benchmark reports how often the guard stops a right
            purchase, not only what it catches.
          </li>
          <li>
            <strong>Limits are stated.</strong> One sport, a catalog we built, a single reviewer, preliminary
            numbers — said on the page, not left out.
          </li>
          <li>
            <strong>Half the dataset stays hidden,</strong> so results on it cannot be tuned.
          </li>
        </ul>

        <h2 id="status"><a href="#status">Status</a></h2>
        <p>
          Draft. The <Link href="/spec">spec</Link> is version 0.1. Benchmark results on this site are preliminary
          (run of {RESULTS.runDate}); real models are being re-run after three fixes to the test bench. Code:{" "}
          <GitHubLink>the repository</GitHubLink>.
        </p>
      </article>
    </main>
  );
}
