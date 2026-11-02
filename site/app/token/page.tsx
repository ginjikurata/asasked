import type { Metadata } from "next";
import { CopyInline } from "@/components/InstallTabs";
import { PageHead } from "@/components/PageHead";
import { GITHUB_URL, OPERATOR, TOKEN } from "@/lib/content";

export const metadata: Metadata = {
  title: "Token",
  description: `$${TOKEN.ticker}, a meme token for AsAsked: what it is, what it is not, and where creator fees go.`,
  alternates: { canonical: "/token" },
};

/** Shown where a fact is not known yet. */
function Missing({ children }: { children: React.ReactNode }) {
  return <span className="text-signal">[{children}]</span>;
}

export default function TokenPage() {
  return (
    <main>
      <PageHead kicker={`Token · $${TOKEN.ticker}`} title="The AsAsked token">
        <p className="text-muted">
          {TOKEN.address ? "We launched" : "We plan to launch"} ${TOKEN.ticker}, a meme token on pump.fun, to pay for
          work on AsAsked. Creator fees from trading {TOKEN.address ? "go" : "will go"} to development. The code stays
          free and open, and nothing about it depends on the token.
        </p>
      </PageHead>
      <article className="doc column">
        <h2 id="companies"><a href="#companies">For companies and standards people</a></h2>
        <p>
          AsAsked remains an open reference under Apache-2.0. The guard, the sandbox store, the benchmark and the open
          dataset work the same whether or not anyone holds the token. The token {TOKEN.address ? "is" : "will be"} how we fund development; it
          is not part of the guard and is never needed to use it.
        </p>

        <h2 id="not"><a href="#not">What the token is not</a></h2>
        <ul>
          <li>Not a share in AsAsked or Concord, and not a claim on any income.</li>
          <li>No voting rights, no access to anything, no promise of a price or a return.</li>
          <li>Not financial advice. Meme tokens can lose all their value.</li>
        </ul>

        <h2 id="address"><a href="#address">The only real address</a></h2>
        <p>
          Anyone can launch a token with the same name. The real ${TOKEN.ticker} exists only on Solana, where pump.fun
          runs, and is the one with this address, on this page:
        </p>
        <p className="font-mono break-all">
          {TOKEN.address ? <CopyInline>{TOKEN.address}</CopyInline> : <Missing>not launched yet</Missing>}
        </p>
        {(TOKEN.address || TOKEN.x) && (
          <ul>
            {TOKEN.address && (
              <>
                <li>
                  <a href={`https://pump.fun/coin/${TOKEN.address}`}>pump.fun</a>
                </li>
                <li>
                  <a href={`https://dexscreener.com/solana/${TOKEN.address}`}>DEX Screener</a>
                </li>
              </>
            )}
            {TOKEN.x && (
              <li>
                Our X account: <a href={TOKEN.x}>{TOKEN.x.replace("https://", "")}</a>
              </li>
            )}
          </ul>
        )}
        <p>
          If an address anywhere else differs from this one, it is not ours. If you see a fake, tell us at{" "}
          <a href={`mailto:${OPERATOR.email}`}>{OPERATOR.email}</a>.
        </p>
        <p>
          The token is launched by Ginji Kurata, who does not buy it. The creator wallet that receives the fees is
          shown on the token&apos;s pump.fun page, so anyone can check what comes in and goes out.
        </p>

        <h2 id="spending"><a href="#spending">Where the money goes</a></h2>
        {TOKEN.spending.length ? (
          <ul>
            {TOKEN.spending.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : (
          <p>
            <Missing>list of expenses</Missing>
          </p>
        )}
        <p>Each month we publish what came in from creator fees and what it was spent on.</p>

        <h2 id="scams"><a href="#scams">What we never do</a></h2>
        <ul>
          <li>We never message you first, on any platform.</li>
          <li>We never ask for your seed phrase, private key or wallet access.</li>
          <li>We run no giveaways and no airdrops.</li>
        </ul>
        <p>Anyone who does any of this in our name is not us.</p>

        <h2 id="no-fees"><a href="#no-fees">If the fees stop</a></h2>
        <p>
          AsAsked continues: the code is open and does not depend on the token. Development may slow down, though, as
          the fees pay for model runs, the server and time.
        </p>

        <h2 id="reports"><a href="#reports">Monthly reports</a></h2>
        {TOKEN.reports.length ? (
          <ul>
            {TOKEN.reports.map((r) => (
              <li key={r.month}>
                <strong>{r.month}.</strong> {r.text}
              </li>
            ))}
          </ul>
        ) : (
          <p>No reports yet: the first comes one month after launch.</p>
        )}
        <p>
          Code: <a href={GITHUB_URL}>github.com/ginjikurata/asasked</a>. Every change to this page is public: see the
          history of the <a href={`${GITHUB_URL}/commits/main/site/app/token/page.tsx`}>page</a> and of the{" "}
          <a href={`${GITHUB_URL}/commits/main/site/lib/content.ts`}>address and spending list</a>.
        </p>
      </article>
    </main>
  );
}
