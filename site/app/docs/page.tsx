import type { Metadata } from "next";
import Link from "next/link";
import { GitHubLink } from "@/components/Chrome";
import { PageHead } from "@/components/PageHead";
import { GITHUB_URL, PYPI_URL, RELEASE_URL, VERSION, VI_URL } from "@/lib/content";

export const metadata: Metadata = {
  title: "Docs",
  description: "Install the guard, check a cart, run the sandbox store and the benchmark on your own agent.",
  alternates: { canonical: "/docs" },
};

// Install commands follow README.md and docs/install.md, the source of truth for them.
const INSTALL = `pip install asasked`;

const EXTRAS: [string, string][] = [
  ["asasked[anthropic]", "Claude as an extractor; Gemini and OpenAI-compatible endpoints need nothing extra"],
  ["asasked[mcp]", "the MCP server, asasked-mcp"],
  ["asasked[claude-agent]", "the hook for Claude Agent SDK"],
  ["asasked[openai-agents]", "the guardrail for OpenAI Agents SDK"],
  ["asasked[langchain]", "the middleware for LangChain 1.x"],
];

const MCP = `# A. nothing to install first, with uv
uvx --from "asasked[mcp,anthropic]" asasked-mcp

# B. installed with pip
pip install "asasked[mcp,anthropic]"
which asasked-mcp                  # the full path to put in the app's config`;

const SOURCE = `git clone ${VI_URL}.git
git clone ${GITHUB_URL}.git
cd asasked
python3 -m venv .venv && source .venv/bin/activate
pip install -e ../verifiable-intent -e ".[dev]"
pip install -e ".[anthropic]"     # if Claude extracts`;

const ENV = `# environment variables; in a checkout, copy .env.example
# the two extractors to compare
LLM_AGREE_PROVIDERS=gemini,anthropic

LLM_API_KEY=...             # Gemini, Google's own API
CLAUDE_API_KEY=...          # Claude (CLAUDE_BASE_URL: a proxy)
OPENAI_COMPAT_BASE_URL=...  # any /chat/completions
OPENAI_COMPAT_API_KEY=...
OPENAI_COMPAT_MODEL=...`;

const CHECK = `from asasked.guard import Guard
from asasked.store.store import Mandate, Store

store = Store()   # the sandbox catalog; in production, your own find()
sku = "ASI-GELRESOLUTION9-42-BLA-OUT"
mandate = Mandate(prompt_summary="Black ASICS, size 42, returnable",
                  allowlist=(sku,), quantity_cap=1,
                  amount_min_cents=0, amount_max_cents=20000)

guard = Guard(request="Black ASICS in size 42, I need to be able to return them.",
              today="Monday, 2 November 2026")
guard.check([(sku, 1)], mandate, store.find)`;

const CHECK_OUT = `{'decision': 'ask',
 'reasons': ['Asked to be able to return it, the item is final sale:
              ASICS Gel-Resolution 9, size 42, black.'],
 'question': 'Before I buy this, please check:\\n'
             '  - Asked to be able to return it, the item is final sale:
                  ASICS Gel-Resolution 9, size 42, black.\\n'
             'Should I still go ahead?',
 'notes': []}`;

const STORE = `session = store.new_session(mandate, guard=guard, guard_mode="enforced")
session.call("search_products", {"query": "black asics 42", "limit": 2})
session.call("add_to_cart", {"sku": sku, "quantity": 1})
session.call("checkout", {"confirm": True})`;

const STORE_OUT = `{'status': 'needs_confirmation',
 'reasons': ['Asked to be able to return it, the item is final sale: ...'],
 'question': 'Before I buy this, please check: ...',
 'next_step': 'Ask the person with ask_user. If they agree, call checkout
               again; otherwise change the cart or stop.'}`;

const HTTP = `python scripts/serve_store.py --port 8765

GET  /tools                     the tools, as JSON schemas
POST /sessions                  {"mandate": {...}, "user_reply": "..."}
POST /sessions/<id>/call        {"tool": "search_products", "args": {...}}
GET  /sessions/<id>/transcript  every call and the final order`;

const BENCH = `python scripts/run_agents.py --tasks v1-open --guard both \\
    --agents naive
python scripts/run_agents.py --tasks v1-open --guard both \\
    --agents claude-sonnet-5,gpt-6-sol --parallel 8
python scripts/run_agents.py --tasks v1-open --guard both \\
    --agents openai_compat:your/model`;

const FIELDS: [string, string][] = [
  ["name, brand", "what the item is; brand is compared case-insensitively"],
  ["color, size_label, level", "variant attributes; level is beginner, intermediate, pro or any"],
  ["refundable", "whether the item can be returned"],
  ["ships_in_days", "days until it arrives"],
  ["price_cents", "price in minor units"],
  ["units (optional)", "how many the person would count: a 4-can pack is 4"],
];

function Code({ children, title }: { children: string; title?: string }) {
  return (
    <figure>
      {title && <figcaption className="meta mb-1">{title}</figcaption>}
      <pre>
        <code>{children}</code>
      </pre>
    </figure>
  );
}

export default function DocsPage() {
  return (
    <main>
      <PageHead kicker="Docs" title="Check a cart before it is paid for">
        <p className="text-muted">
          The guard is a Python library. Give it the person&apos;s words and the cart; it answers{" "}
          <code className="font-mono">proceed</code> or <code className="font-mono text-signal">ask</code>. The
          sandbox store and the benchmark run your agent against the same traps we use.
        </p>
      </PageHead>

      <article className="doc column">
        <h2 id="install"><a href="#install">1. Install</a></h2>
        <p>
          Python 3.10 or newer. The guard is one package,{" "}
          <a href={PYPI_URL} className="link">
            asasked on PyPI
          </a>
          ; its only required dependency is <code>cryptography</code>. The same files are attached to the{" "}
          <a href={RELEASE_URL} className="link">
            v{VERSION} release
          </a>{" "}
          on GitHub, for installing without PyPI.
        </p>
        <Code>{INSTALL}</Code>
        <p>Extras add what you use:</p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>extra</th>
                <th>adds</th>
              </tr>
            </thead>
            <tbody>
              {EXTRAS.map(([e, a]) => (
                <tr key={e}>
                  <td>
                    <code>{e}</code>
                  </td>
                  <td>{a}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p>
          <strong>As an MCP server.</strong> <code>asasked-mcp</code> is a local (stdio) server with one tool,{" "}
          <code>check_order</code>, that the agent calls before paying. It is a second opinion the agent chooses to
          ask for, not a lock: if payment goes through your own code, call the guard there instead.
        </p>
        <Code>{MCP}</Code>
        <p>
          Ready configs for Claude Code, Claude Desktop, Cursor, VS Code, Codex CLI and Gemini CLI are in{" "}
          <GitHubLink path="/blob/main/docs/install.md">docs/install.md</GitHubLink>.
        </p>
        <p>
          <strong>From source,</strong> to run the sandbox store and reproduce the benchmark (sections 5–7). Checkout
          in the store builds a real Verifiable Intent chain, so the reference SDK is expected as a sibling checkout:
        </p>
        <Code>{SOURCE}</Code>

        <h2 id="models"><a href="#models">2. Choose the extractors</a></h2>
        <p>
          Turning words into facts is the only step that uses a model, and it uses two of them. Any two of Gemini,
          Claude and an OpenAI-compatible endpoint will do. The decision itself is plain code.
        </p>
        <Code title=".env">{ENV}</Code>

        <h2 id="check"><a href="#check">3. Check a cart</a></h2>
        <p>
          Facts are extracted once per request; each <code>check</code> compares them with a cart. Pass{" "}
          <code>today</code>, so that “by Saturday” becomes a number of days.
        </p>
        <Code title="python">{CHECK}</Code>
        <Code title="result">{CHECK_OUT}</Code>
        <p>
          <code>reasons</code> block the purchase; <code>notes</code> are mismatches on facts the person marked as
          optional, or that the two models disagreed on. If extraction fails, the guard answers <code>ask</code>:
          it fails closed. For tests or replays, pass <code>extract=</code> with ready facts instead of calling
          models.
        </p>

        <h2 id="catalog"><a href="#catalog">4. Your own catalog</a></h2>
        <p>
          <code>find(sku)</code> returns the item as a dict. These are the attributes the checks read; a check whose
          attribute is missing cannot run.
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>field</th>
                <th>meaning</th>
              </tr>
            </thead>
            <tbody>
              {FIELDS.map(([f, m]) => (
                <tr key={f}>
                  <td>
                    <code>{f}</code>
                  </td>
                  <td>{m}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p>
          The mandate supplies the amount band and the allowlist, so the guard can tell “expensive” from “there was
          nothing cheaper”.
        </p>

        <h2 id="store"><a href="#store">5. The sandbox store</a></h2>
        <p>
          A deterministic store with 456 products from 4 merchants, driven through tools:{" "}
          <code>search_products</code>, <code>get_product</code>, <code>add_to_cart</code>,{" "}
          <code>remove_from_cart</code>, <code>view_cart</code>, <code>ask_user</code>, <code>checkout</code>. Every
          order goes through a real Verifiable Intent chain. The guard runs in one of three modes:{" "}
          <code>off</code>, <code>advisory</code> (the agent gets a <code>check_before_checkout</code> tool) or{" "}
          <code>enforced</code> (checkout holds the order until the agent has asked the person).
        </p>
        <Code title="python">{STORE}</Code>
        <Code title="checkout, enforced">{STORE_OUT}</Code>
        <p>Agents outside Python reach the same store over HTTP on localhost:</p>
        <Code>{HTTP}</Code>

        <h2 id="benchmark"><a href="#benchmark">6. Run the benchmark</a></h2>
        <p>
          The same agent runs each task without the guard and with it enforced. Every run is one JSON line in{" "}
          <code>runs/</code> with the full tool-call transcript. Agents are scored against the human label, not
          against the guard: a right purchase, a wrong purchase that payment let through, or no purchase.
        </p>
        <Code>{BENCH}</Code>
        <p>
          The open half of the dataset is in the repository; see <Link href="/dataset">Dataset</Link>. The hidden
          half is kept for evaluation.
        </p>

        <h2 id="tests"><a href="#tests">7. Tests</a></h2>
        <p>
          <code>pytest</code> covers the deterministic check, the Verifiable Intent chain, the store and the
          harness, with no model and no network. The behaviour every implementation must match is in the{" "}
          <Link href="/spec">spec</Link>.
        </p>
        <Code>{`pytest -q`}</Code>

        <p className="meta pt-6">
          Code: <GitHubLink>the repository</GitHubLink> · every snippet on this page was run against it
        </p>
      </article>
    </main>
  );
}
