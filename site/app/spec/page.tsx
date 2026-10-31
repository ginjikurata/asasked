import { readFileSync } from "node:fs";
import path from "node:path";
import type { Metadata } from "next";
import { Marked } from "marked";
import { GitHubLink } from "@/components/Chrome";
import { PageHead } from "@/components/PageHead";

export const metadata: Metadata = {
  title: "Spec",
  description: "What a pre-checkout guard must do: intent facts, extraction, checks, decision, conformance.",
  alternates: { canonical: "/spec" },
};

const capitalise = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

const slug = (s: string) =>
  s.toLowerCase().replace(/<[^>]+>/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

/**
 * The spec is the repository's spec/guard.md, read at build time, so the site and the document
 * can never say different things. Its title and status line become the page head.
 */
function loadSpec() {
  const source = readFileSync(path.join(process.cwd(), "..", "spec", "guard.md"), "utf8");
  const lines = source.split("\n");
  const title = lines[0].replace(/^#\s*/, "");
  const statusAt = lines.findIndex((l) => l.startsWith("**Status:**"));
  // the status paragraph runs until the first blank line
  const statusEnd = lines.findIndex((l, i) => i > statusAt && l.trim() === "");
  const status = lines.slice(statusAt, statusEnd).join(" ").replace("**Status:**", "").trim();
  const body = lines.slice(statusEnd + 1).join("\n");

  const toc: { id: string; text: string }[] = [];
  const md = new Marked({
    renderer: {
      heading({ tokens, depth, text }) {
        const html = this.parser.parseInline(tokens);
        const id = slug(text);
        if (depth === 2) toc.push({ id, text });
        return `<h${depth} id="${id}"><a href="#${id}">${html}</a></h${depth}>\n`;
      },
    },
  });
  return { title, status, html: md.parse(body) as string, toc };
}

export default function SpecPage() {
  const { title, status, html, toc } = loadSpec();
  const statusHtml = new Marked().parseInline(status) as string;
  return (
    <main>
      <PageHead kicker="Specification" title={capitalise(title.replace(/^AsAsked\s*/, ""))}>
        <p className="text-muted" dangerouslySetInnerHTML={{ __html: statusHtml }} />
        <p className="meta mt-4">
          Source: <GitHubLink path="/blob/main/spec/guard.md">spec/guard.md</GitHubLink> · this page is built from it
        </p>
      </PageHead>
      <div className="column">
        <nav aria-label="Contents" className="receipt px-4 pt-3 font-mono text-[13px]">
          <p className="meta mb-2">contents</p>
          <ol className="grid gap-x-8 gap-y-1 sm:grid-cols-2">
            {toc.map((h) => (
              <li key={h.id}>
                <a href={`#${h.id}`} className="link">
                  {h.text}
                </a>
              </li>
            ))}
          </ol>
        </nav>
        <article className="doc mt-12" dangerouslySetInnerHTML={{ __html: html }} />
      </div>
    </main>
  );
}
