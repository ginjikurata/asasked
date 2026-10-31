import type { Metadata } from "next";
import Link from "next/link";
import { PageHead } from "@/components/PageHead";
import { CONCORD_URL, OPERATOR } from "@/lib/content";

export const metadata: Metadata = {
  title: "Legal notice",
  description: "Who runs asasked.dev and how to reach them.",
  alternates: { canonical: "/legal" },
};

export default function LegalPage() {
  return (
    <main>
      <PageHead kicker={`Legal · last updated ${OPERATOR.updated}`} title="Legal notice">
        <p className="text-muted">Who runs this site and how to reach them. It sells nothing and offers no contracts.</p>
      </PageHead>
      <article className="doc column">
        <h2 id="operator"><a href="#operator">Who runs this site</a></h2>
        <p>
          asasked.dev is run privately by the two founders of <a href={CONCORD_URL}>Concord</a>,{" "}
          {OPERATOR.founders}. Concord is not a registered company: it is the name the founders use for their studio
          and its projects. There is no commercial activity on this site.
        </p>
        <p>
          Email: <a href={`mailto:${OPERATOR.email}`}>{OPERATOR.email}</a>
        </p>

        <h2 id="hosting"><a href="#hosting">Hosting</a></h2>
        <p>The site runs on {OPERATOR.hosting}. Pages are delivered over HTTPS.</p>

        <h2 id="content"><a href="#content">Content and links</a></h2>
        <p>
          We write these pages with care and every figure on them comes from the AsAsked repository, but we cannot
          guarantee that everything is complete, correct or current at all times. If you notice an error, tell us and we
          will fix it.
        </p>
        <p>
          The site links to other sites, such as the Verifiable Intent repository. Their operators are responsible for
          what they publish. AsAsked is not affiliated with Verifiable Intent&apos;s authors, Mastercard or Google.
        </p>

        <h2 id="copyright"><a href="#copyright">Copyright, code and fonts</a></h2>
        <p>
          The AsAsked code and the open half of the dataset are published under the Apache-2.0 licence. The text and
          design of this site belong to the founders of Concord unless stated otherwise. The site is set in Inter Tight
          and IBM Plex Mono, published under the SIL Open Font License.
        </p>

        <h2 id="privacy"><a href="#privacy">Privacy</a></h2>
        <p>
          How the site handles personal data is described in the <Link href="/privacy">privacy policy</Link>. In short:
          no accounts, no analytics, no cookies; requests typed into the live demo go to AI model providers and are not stored.
        </p>
      </article>
    </main>
  );
}
