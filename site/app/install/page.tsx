import type { Metadata } from "next";
import Link from "next/link";
import { GitHubLink } from "@/components/Chrome";
import { CopyCode, type InstallTab, InstallTabs } from "@/components/InstallTabs";
import { PageHead } from "@/components/PageHead";
import { PYPI_URL, RELEASE_URL, VERSION } from "@/lib/content";

export const metadata: Metadata = {
  title: "Install",
  description:
    "Add the AsAsked guard to Claude Code, Claude Desktop, Cursor, VS Code, Codex CLI, Gemini CLI or your own Python agent.",
  alternates: { canonical: "/install" },
};

// Every config here follows docs/install.md, the source of truth for them.
const SERVER = `"--from", "asasked[mcp,anthropic]", "asasked-mcp"`;

const CLAUDE_CODE = `claude mcp add --env CLAUDE_API_KEY=your-key --transport stdio asasked -- uvx --from "asasked[mcp,anthropic]" asasked-mcp`;

const CLAUDE_CODE_JSON = `{
  "mcpServers": {
    "asasked": {
      "command": "uvx",
      "args": [${SERVER}],
      "env": {"CLAUDE_API_KEY": "\${CLAUDE_API_KEY}"}
    }
  }
}`;

const CLAUDE_DESKTOP = `{
  "mcpServers": {
    "asasked": {
      "command": "uvx",
      "args": [${SERVER}],
      "env": {"CLAUDE_API_KEY": "your-key"}
    }
  }
}`;

const CURSOR = `{
  "mcpServers": {
    "asasked": {
      "type": "stdio",
      "command": "uvx",
      "args": [${SERVER}],
      "env": {"CLAUDE_API_KEY": "\${env:CLAUDE_API_KEY}"}
    }
  }
}`;

const VSCODE = `{
  "inputs": [
    {"type": "promptString", "id": "claude-key", "description": "Claude API key", "password": true}
  ],
  "servers": {
    "asasked": {
      "type": "stdio",
      "command": "uvx",
      "args": [${SERVER}],
      "env": {"CLAUDE_API_KEY": "\${input:claude-key}"}
    }
  }
}`;

const CODEX = `codex mcp add asasked --env CLAUDE_API_KEY=your-key -- uvx --from "asasked[mcp,anthropic]" asasked-mcp`;

const CODEX_TOML = `[mcp_servers.asasked]
command = "uvx"
args = ["--from", "asasked[mcp,anthropic]", "asasked-mcp"]
env_vars = ["CLAUDE_API_KEY"]`;

const GEMINI = `{
  "mcpServers": {
    "asasked": {
      "command": "uvx",
      "args": ["--from", "asasked[mcp]", "asasked-mcp"],
      "env": {"LLM_API_KEY": "$LLM_API_KEY"}
    }
  }
}`;

const OTHER = `command: uvx
args:    --from "asasked[mcp,anthropic]" asasked-mcp
env:     CLAUDE_API_KEY=your-key`;

const PIP = `pip install "asasked[mcp,anthropic]"
which asasked-mcp     # Windows: where asasked-mcp`;

const PYTHON_INSTALL = `pip install "asasked[anthropic]"`;

const PYTHON = `from asasked import Guard

guard = Guard("Black ASICS in size 42, I need to be able to return them.")

# checkout is your payment function; cart turns its arguments
# into a list of dicts (name, brand, color, size, price, returnable, ...)
pay = guard.protect(checkout, cart=lambda items: items)

# Give the agent pay instead of checkout. If the cart does not match the
# request, checkout is not called: the agent gets "NOT PAID" and a question
# to show the person. Their reply comes from your code, not the agent:
guard.answer("Yes, final sale is fine")`;

const FRAMEWORKS: [string, string, string, string][] = [
  [
    "Claude Agent SDK",
    "asasked[claude-agent]",
    "asasked.integrations.claude_agent",
    `hooks={"PreToolUse": [checkout_hook(guard, cart, tool="mcp__shop__checkout")]}`,
  ],
  [
    "OpenAI Agents SDK",
    "asasked[openai-agents]",
    "asasked.integrations.openai_agents",
    `@function_tool(tool_input_guardrails=[checkout_guardrail(guard, cart)])`,
  ],
  [
    "LangChain 1.x",
    "asasked[langchain]",
    "asasked.integrations.langchain",
    `create_agent(..., middleware=[CheckoutGuard(guard, cart)])`,
  ],
];

const KEYS: [string, string, string][] = [
  ["Claude", "CLAUDE_API_KEY (or ANTHROPIC_API_KEY)", "asasked[anthropic]"],
  ["Gemini", "LLM_API_KEY", "none"],
  ["Any OpenAI-compatible API", "OPENAI_COMPAT_BASE_URL, OPENAI_COMPAT_API_KEY, OPENAI_COMPAT_MODEL", "none"],
];

const TRY = `I asked for black sneakers in size 42. The cart has white sneakers in size 42 for $50. Check the order with check_order.`;

const RestartNote = ({ app }: { app: string }) => (
  <p className="text-muted">
    Restart {app} after saving. If the server does not appear, the app may not see <code>uvx</code>: replace{" "}
    <code>&quot;uvx&quot;</code> with the full path that <code>which uvx</code> prints.
  </p>
);

const TABS: InstallTab[] = [
  {
    id: "claude-code",
    label: "Claude Code",
    content: (
      <>
        <p>Run once in a terminal, with your key in place of <code>your-key</code>:</p>
        <CopyCode title="terminal">{CLAUDE_CODE}</CopyCode>
        <p>
          Add <code>--scope user</code> to have it in every project. To share it with a project through{" "}
          <code>.mcp.json</code>, keep the key in your environment instead of the file:
        </p>
        <CopyCode title=".mcp.json">{CLAUDE_CODE_JSON}</CopyCode>
      </>
    ),
  },
  {
    id: "claude-desktop",
    label: "Claude Desktop",
    content: (
      <>
        <p>
          Settings → Developer → Edit Config opens <code>claude_desktop_config.json</code>. Add the server, with your
          key in place of <code>your-key</code>:
        </p>
        <CopyCode title="claude_desktop_config.json">{CLAUDE_DESKTOP}</CopyCode>
        <p className="text-muted">
          Quit Claude Desktop completely and start it again. If the server does not appear, replace{" "}
          <code>&quot;uvx&quot;</code> with the full path that <code>which uvx</code> prints; on macOS the log is in{" "}
          <code>~/Library/Logs/Claude/mcp-server-asasked.log</code>.
        </p>
      </>
    ),
  },
  {
    id: "cursor",
    label: "Cursor",
    content: (
      <>
        <p>
          <code>~/.cursor/mcp.json</code> for every project, or <code>.cursor/mcp.json</code> in one. The key is read
          from your environment:
        </p>
        <CopyCode title="mcp.json">{CURSOR}</CopyCode>
        <RestartNote app="Cursor" />
      </>
    ),
  },
  {
    id: "vscode",
    label: "VS Code",
    content: (
      <>
        <p>
          For Copilot agent mode: <code>.vscode/mcp.json</code> in a project. VS Code asks for the key the first time
          the server starts and keeps it out of the file.
        </p>
        <CopyCode title=".vscode/mcp.json">{VSCODE}</CopyCode>
      </>
    ),
  },
  {
    id: "codex",
    label: "Codex CLI",
    content: (
      <>
        <p>Run once, with your key in place of <code>your-key</code>:</p>
        <CopyCode title="terminal">{CODEX}</CopyCode>
        <p>
          Or add it to <code>~/.codex/config.toml</code>, passing the key through from your environment:
        </p>
        <CopyCode title="~/.codex/config.toml">{CODEX_TOML}</CopyCode>
      </>
    ),
  },
  {
    id: "gemini",
    label: "Gemini CLI",
    content: (
      <>
        <p>
          In <code>~/.gemini/settings.json</code>, or <code>.gemini/settings.json</code> in a project. This one reads
          requests with Gemini, so it needs <code>LLM_API_KEY</code> in your environment:
        </p>
        <CopyCode title="settings.json">{GEMINI}</CopyCode>
      </>
    ),
  },
  {
    id: "other",
    label: "Other MCP apps",
    content: (
      <>
        <p>Most apps that take MCP servers ask for the same three things:</p>
        <CopyCode>{OTHER}</CopyCode>
        <p>
          Without <code>uv</code>, install the server with pip and use the path the second command prints as the
          command, with no arguments:
        </p>
        <CopyCode title="terminal">{PIP}</CopyCode>
      </>
    ),
  },
  {
    id: "python",
    label: "Your Python agent",
    content: (
      <>
        <p>
          If payment goes through your own code, put the guard there. The agent then cannot pay around it, and it
          cannot answer the question for the person.
        </p>
        <CopyCode title="terminal">{PYTHON_INSTALL}</CopyCode>
        <CopyCode title="python">{PYTHON}</CopyCode>
        <p>Agent frameworks get a ready hook over the same check:</p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>framework</th>
                <th>install</th>
                <th>hook</th>
              </tr>
            </thead>
            <tbody>
              {FRAMEWORKS.map(([name, extra, mod, hook]) => (
                <tr key={name}>
                  <td>{name}</td>
                  <td>
                    <code>{extra}</code>
                  </td>
                  <td>
                    <code>{hook}</code>
                    <br />
                    <span className="text-faint">
                      from <code>{mod}</code>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p>
          The cart format and everything else <code>Guard</code> takes are in the <Link href="/docs">docs</Link>.
        </p>
      </>
    ),
  },
];

export default function InstallPage() {
  return (
    <main>
      <PageHead kicker="Install" title="Add the guard to your agent">
        <p className="text-muted">
          Before your agent pays, AsAsked checks the cart against what the person asked for. In apps like Claude Code
          or Cursor it runs as an MCP server; in your own code it sits in front of checkout. Pick your app below.
        </p>
      </PageHead>

      <div className="column">
        <article className="doc">
          <h2 id="key"><a href="#key">1. A model key</a></h2>
          <p>
            The guard reads the person&apos;s request with a language model, then compares it with the cart in plain
            code. It needs one key, as an environment variable or in the app&apos;s config. Without a key it cannot
            read the request, and every check answers <em>ask</em>.
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>model</th>
                  <th>variable</th>
                  <th>extra</th>
                </tr>
              </thead>
              <tbody>
                {KEYS.map(([m, v, e]) => (
                  <tr key={m}>
                    <td>{m}</td>
                    <td>
                      <code>{v}</code>
                    </td>
                    <td>
                      <code>{e}</code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p>
            The configs below use Claude. For Gemini, drop <code>,anthropic</code> and set <code>LLM_API_KEY</code>{" "}
            instead of <code>CLAUDE_API_KEY</code>. A key written into a config file is stored there in plain text.
          </p>

          <h2 id="app"><a href="#app">2. Your app</a></h2>
          <p>
            The MCP configs start the server with <code>uvx</code>, which downloads and runs the package itself, so
            there is nothing to install first. It comes with{" "}
            <a href="https://docs.astral.sh/uv/">uv</a>. No uv? See “Other MCP apps”.
          </p>
        </article>

        <div className="mt-8">
          <InstallTabs tabs={TABS} />
        </div>

        <article className="doc">
          <h2 id="check"><a href="#check">3. Check that it works</a></h2>
          <p>Ask the agent:</p>
          <CopyCode>{TRY}</CopyCode>
          <p>
            It should come back with <em>ask</em> and a question about the colour. If it answers <em>ask</em> with “I
            couldn&apos;t automatically check this order”, the server runs but has no working key.
          </p>

          <h2 id="lock"><a href="#lock">A second opinion, not a lock</a></h2>
          <p>
            An MCP server answers only when the agent calls it, and it has to take the agent&apos;s word for the request
            and the person&apos;s replies. It helps an agent that wants to get the order right; it cannot stop one that
            skips it. To make sure nothing is paid around the guard, put it in front of your checkout, as in “Your
            Python agent”.
          </p>

          <p className="meta pt-6">
            Package:{" "}
            <a href={PYPI_URL} className="link">
              asasked on PyPI
            </a>{" "}
            ·{" "}
            <a href={RELEASE_URL} className="link">
              v{VERSION} release
            </a>{" "}
            · the same configs in <GitHubLink path="/blob/main/docs/install.md">docs/install.md</GitHubLink>
          </p>
        </article>
      </div>
    </main>
  );
}
