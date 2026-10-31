import type { Metadata } from "next";
import Link from "next/link";
import { PageHead } from "@/components/PageHead";
import { OPERATOR } from "@/lib/content";

export const metadata: Metadata = {
  title: "Privacy policy",
  description: "What asasked.dev does with your data: nothing it does not need to deliver the page.",
  alternates: { canonical: "/privacy" },
};

export default function PrivacyPage() {
  return (
    <main>
      <PageHead kicker={`Privacy · last updated ${OPERATOR.updated}`} title="Privacy policy">
        <p className="text-muted">
          In short: this site is a set of pages to read. It has no forms, no accounts and no analytics, sets no cookies
          and stores nothing in your browser. If you email us, we use your message to reply.
        </p>
      </PageHead>
      <article className="doc column">
        <h2 id="who"><a href="#who">Who is responsible</a></h2>
        <p>
          The site is run privately by the two founders of Concord, {OPERATOR.founders}. Concord is not a registered
          company, and the site is not run for profit. “We” and “us” mean the two founders. This policy covers
          asasked.dev.
        </p>

        <h2 id="not"><a href="#not">What the site does not do</a></h2>
        <ul>
          <li>No cookies, and nothing stored in your browser.</li>
          <li>No visitor statistics, tracking pixels or fingerprinting.</li>
          <li>No sign-up, no login, no newsletter, no email capture.</li>
          <li>No third parties in the page: no ads, videos, maps or social widgets. Fonts come from our own server.</li>
        </ul>
        <p>
          The pages run scripts for the pixel background, the demo and the dataset filter, and to load the next page
          from our own server when you follow a link. They send nothing to anyone. The background reacts to your cursor
          position on your screen; it is not recorded or sent anywhere. If any of this changes, we will update this
          policy before the change goes live.
        </p>

        <h2 id="server"><a href="#server">What any web server receives</a></h2>
        <p>
          To send you a page, a web server receives the date and time of the request, the page requested, your
          browser&apos;s user agent and, if your browser sends it, the page you came from. Our server uses this only to
          deliver the page and is configured not to keep a request log. It is {OPERATOR.hosting}; the connection is
          encrypted with HTTPS.
        </p>

        <h2 id="email"><a href="#email">If you email us</a></h2>
        <p>
          If you write to <a href={`mailto:${OPERATOR.email}`}>{OPERATOR.email}</a>, we receive your address, your
          name if you include it and your message. We use it only to answer you, keep it as long as the conversation
          needs or until you ask us to delete it, and share it with no one but the services that carry the mail.
        </p>

        <h2 id="rights"><a href="#rights">Your rights</a></h2>
        <p>
          Where data protection law such as the GDPR applies, we rely on our legitimate interest in delivering the site
          and answering messages you choose to send. You may have the right to ask what we hold about you, have it
          corrected or deleted, restrict or object to its use, and receive it in a portable format. Write to us to use
          any of these rights; you can also complain to the data protection authority where you live.
        </p>
        <p>
          See also the <Link href="/legal">legal notice</Link>.
        </p>
      </article>
    </main>
  );
}
