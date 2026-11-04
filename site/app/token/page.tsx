import type { Metadata } from "next";
import { CopyInline } from "@/components/InstallTabs";
import { PageHead } from "@/components/PageHead";
import { GITHUB_URL, OPERATOR, TOKEN } from "@/lib/content";

export const metadata: Metadata = {
  title: "Token",
  description: `$${TOKEN.ticker}, a token for AsAsked: what it is, what it is not, and where creator fees go.`,
  alternates: { canonical: "/token" },
  openGraph: {
    type: "website",
    siteName: "AsAsked",
    url: "/token",
    title: `The AsAsked token ($${TOKEN.ticker})`,
    description: `$${TOKEN.ticker}, a token on pump.fun that pays for work on AsAsked. The code stays free and open.`,
    // A page-level openGraph replaces the root one, image included, so the site image is named again here.
    images: ["/opengraph-image"],
  },
  twitter: {
    card: "summary_large_image",
    title: `The AsAsked token ($${TOKEN.ticker})`,
    description: `$${TOKEN.ticker}, a token on pump.fun that pays for work on AsAsked. The code stays free and open.`,
    images: ["/opengraph-image"],
  },
};

/** Shown where a fact is not known yet. */
function Missing({ children }: { children: React.ReactNode }) {
  return <span className="text-signal">[{children}]</span>;
}

const fmt = (n: number) => Math.round(n).toLocaleString("en-US");

/** Burned from creator fees so far, against the 2% goal. Figures come from TOKEN.burns, each with its transactions. */
function BurnProgress() {
  const burned = TOKEN.burns.reduce((sum, b) => sum + b.amount, 0);
  const share = Math.min(burned / TOKEN.burnTarget, 1);
  const pct = (share * 100).toFixed(1);
  return (
    <>
      <div className="mt-6">
        <div className="meta flex flex-wrap justify-between gap-x-4">
          <span>Burned from fees · {fmt(burned)}</span>
          <span>Goal · {fmt(TOKEN.burnTarget)} (2% of supply)</span>
        </div>
        <div
          className="relative mt-2 h-3 w-full bg-panel"
          role="progressbar"
          aria-label="Tokens burned from creator fees, against the goal"
          aria-valuemin={0}
          aria-valuemax={TOKEN.burnTarget}
          aria-valuenow={Math.round(burned)}
          aria-valuetext={`${fmt(burned)} of ${fmt(TOKEN.burnTarget)} tokens, ${pct}%`}
        >
          <div className="h-full bg-signal" style={{ width: `${Math.max(share * 100, burned > 0 ? 0.6 : 0)}%` }} />
        </div>
        <p className="meta mt-2">{pct}% of the goal</p>
      </div>
      <p>
        Part of the creator fees buys back ${TOKEN.ticker}, which is then burned on chain: the total supply goes down,
        and nobody can get those tokens back. The goal is 2% of the {fmt(TOKEN.supply)} supply. That is a first goal, not a limit: we may burn more
        after it. The launcher&apos;s
        353,134 tokens do not count toward it. A burn is not a promise of a price.
      </p>
      {TOKEN.burns.length > 0 && (
        <ul>
          {TOKEN.burns.map((b) => (
            <li key={b.burnTx}>
              {b.date}: {fmt(b.amount)} burned (<a href={`https://solscan.io/tx/${b.buyTx}`}>buyback</a>,{" "}
              <a href={`https://solscan.io/tx/${b.burnTx}`}>burn</a>).
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

export default function TokenPage() {
  return (
    <main>
      <PageHead kicker={`Token · $${TOKEN.ticker}`} title="The AsAsked token">
        <p className="text-muted">
          {TOKEN.launched ? "We launched" : "We plan to launch"} ${TOKEN.ticker}, a token on pump.fun, to pay for
          work on AsAsked. Creator fees from trading {TOKEN.launched ? "go" : "will go"} to development. The code stays
          free and open, and nothing about it depends on the token.
        </p>
        <p className="meta mt-8">Contract address · Solana</p>
        <p className="mt-2 font-mono text-[15px] break-all md:text-base">
          {TOKEN.address ? <CopyInline>{TOKEN.address}</CopyInline> : <Missing>{TOKEN.launched ? "address coming soon" : "not launched yet"}</Missing>}
        </p>
        {(TOKEN.address || TOKEN.x || TOKEN.telegram) && (
          <p className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-[15px]">
            {TOKEN.address && (
              <>
                <a href={`https://pump.fun/coin/${TOKEN.address}`} className="link">
                  pump.fun
                </a>
                <a href={`https://dexscreener.com/solana/${TOKEN.address}`} className="link">
                  DEX Screener
                </a>
              </>
            )}
            {TOKEN.x && (
              <a href={TOKEN.x} className="link">
                X: {TOKEN.x.replace("https://x.com/", "@")}
              </a>
            )}
            {TOKEN.telegram && (
              <a href={TOKEN.telegram} className="link">
                Telegram: {TOKEN.telegram.replace("https://", "")}
              </a>
            )}
          </p>
        )}
      </PageHead>
      <article className="doc column">
        <h2 id="companies"><a href="#companies">For companies and standards people</a></h2>
        <p>
          AsAsked remains an open reference under Apache-2.0. The guard, the sandbox store, the benchmark and the open
          dataset work the same whether or not anyone holds the token. The token {TOKEN.launched ? "is" : "will be"} how we fund development; it
          is not part of the guard and is never needed to use it.
        </p>

        <h2 id="not"><a href="#not">What the token is not</a></h2>
        <ul>
          <li>Not a share in AsAsked or Concord, and not a claim on any income.</li>
          <li>No voting rights, no access to anything, no promise of a price or a return.</li>
          <li>Not financial advice. Tokens like this can lose all their value.</li>
        </ul>

        <h2 id="address"><a href="#address">The only real address</a></h2>
        <p>
          Anyone can launch a token with the same name. The real ${TOKEN.ticker} exists only on Solana, where pump.fun
          runs, and is the one with the address at the top of this page.
        </p>
        <p>
          If an address anywhere else differs from this one, it is not ours. If you see a fake, tell us at{" "}
          <a href={`mailto:${OPERATOR.email}`}>{OPERATOR.email}</a>.
        </p>
        <p>
          The token is launched by Ginji Kurata, who holds none of it: all 353,134 tokens in his wallet were sent to
          the Solana incinerator address and cannot be recovered (
          <a href="https://solscan.io/tx/4TJQnu2uQNtZMFqHGh3madvBS3ERbkBwuwmSG7jMmiHH8qaUevzsCVbF5mGFLp6XnJG74SSbCMVxQCwhkWseHUBc">
            transaction
          </a>
          ). The creator wallet that receives the fees is shown on the token&apos;s pump.fun page, so anyone can check
          what comes in and goes out.
        </p>

        <h2 id="tokenomics"><a href="#tokenomics">Tokenomics</a></h2>
        <ul>
          <li>Launched on pump.fun on 2 November 2026. No presale, no team allocation.</li>
          <li>
            Total supply at launch: {fmt(TOKEN.supply)} tokens, sold only on the open pump.fun curve. Nobody can mint
            more or freeze accounts: both authorities are revoked on chain.
          </li>
          <li>The launcher holds 0%: his 353,134 tokens were sent to the incinerator address, as above.</li>
          <li>
            Creator fees are the only income. They are split as below, and each monthly report shows the split with
            receipts and burn transactions.
          </li>
        </ul>

        <h2 id="spending"><a href="#spending">Where the money goes</a></h2>
        <ul>
          {TOKEN.split.map((s) => (
            <li key={s.what}>
              <strong>{s.pct}%</strong> {s.what}
            </li>
          ))}
        </ul>
        <p>
          The split can change; any change is dated on this page and in the next monthly report. The shares for
          buyback and burn and for bug bounties are fixed. While the fees are small, the 30% for development time may
          go instead to hosting and the domain, the X checkmark and development tools. The monthly report shows what
          that share was actually spent on, with receipts.
        </p>
        <p>In more detail:</p>
        {TOKEN.spending.length ? (
          <ul>
            {TOKEN.spending.map((item) => (
              <li key={item.text}>
                {item.text}
                {item.paid && <> <span className="underline underline-offset-4">{item.paid}</span></>}
              </li>
            ))}
          </ul>
        ) : (
          <p>
            <Missing>list of expenses</Missing>
          </p>
        )}
        <p>Each month we publish what came in from creator fees and what it was spent on.</p>

        <h2 id="burn"><a href="#burn">Buyback and burn</a></h2>
        <BurnProgress />

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
