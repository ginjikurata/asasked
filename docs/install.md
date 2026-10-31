# Installing AsAsked

AsAsked is one Python package, [`asasked` on PyPI](https://pypi.org/project/asasked/).
The same files are attached to each
[GitHub release](https://github.com/ginjikurata/asasked/releases).
It needs Python 3.10 or newer.

| You want | Install |
|---|---|
| The guard in your own Python code | `pip install asasked` |
| The guard as an MCP server for an agent app | `pip install "asasked[mcp,anthropic]"`, or nothing with `uvx` (below) |
| A hook for Claude Agent SDK, OpenAI Agents SDK or LangChain | `pip install "asasked[claude-agent]"`, `"asasked[openai-agents]"` or `"asasked[langchain]"` |
| Without PyPI | download the `.whl` from a release, then `pip install asasked-<version>-py3-none-any.whl` |

## A model key

The guard reads the person's request with a language model, then compares
it with the cart in plain code. It needs at least one key, passed as an
environment variable:

| Model | Variable | Extra |
|---|---|---|
| Claude | `CLAUDE_API_KEY` (or `ANTHROPIC_API_KEY`) | `asasked[anthropic]` |
| Gemini | `LLM_API_KEY` | none |
| Any OpenAI-compatible API | `OPENAI_COMPAT_BASE_URL`, `OPENAI_COMPAT_API_KEY`, `OPENAI_COMPAT_MODEL` | none |

With two keys, both models read the request and their disagreements become
visible. With no key, every check answers *ask*: the guard fails closed.

## The MCP server

`asasked-mcp` is a local (stdio) MCP server with one tool,
`check_order(request, cart, answers)`. The agent calls it before paying; on
*ask* it shows the person the question and checks again with the reply.
It is a second opinion the agent chooses to ask for, not a lock — see
[the README](../README.md#the-pre-checkout-guard) for what that means and
how to put the guard into the payment step instead.

There are two ways to start it. Pick one and use it in the config of your
app below.

**A. With `uvx`, nothing to install first.** If you have
[uv](https://docs.astral.sh/uv/), the app can fetch and run the package
itself:

```
command: uvx
args:    --from "asasked[mcp,anthropic]" asasked-mcp
```

**B. Installed with pip.**

```bash
pip install "asasked[mcp,anthropic]"
```

```bash
which asasked-mcp
```

The second command prints the full path to the server (on Windows,
`where asasked-mcp`). Use that path as `command`, with no `args`.

Desktop apps such as Claude Desktop and Cursor are often started without
your shell's `PATH`, so a bare `uvx` or `asasked-mcp` may not be found.
If the server does not appear, replace the command with its full path
(`which uvx` or `which asasked-mcp`).

The examples use `uvx` and Claude. For Gemini, drop `,anthropic` and set
`LLM_API_KEY` instead of `CLAUDE_API_KEY`. A key written into a config file
is stored there in plain text; where the app can read it from your
environment instead, the example shows how.

### Claude Code

```bash
claude mcp add --env CLAUDE_API_KEY=your-key --transport stdio asasked -- uvx --from "asasked[mcp,anthropic]" asasked-mcp
```

Add `--scope user` to have it in every project. To share it with a project
through `.mcp.json`, keep the key in your environment:

```json
{
  "mcpServers": {
    "asasked": {
      "command": "uvx",
      "args": ["--from", "asasked[mcp,anthropic]", "asasked-mcp"],
      "env": {"CLAUDE_API_KEY": "${CLAUDE_API_KEY}"}
    }
  }
}
```

### Claude Desktop

Settings → Developer → Edit Config opens `claude_desktop_config.json`
(macOS: `~/Library/Application Support/Claude/`, Windows: `%APPDATA%\Claude\`,
Linux: `~/.config/Claude/`). Add:

```json
{
  "mcpServers": {
    "asasked": {
      "command": "uvx",
      "args": ["--from", "asasked[mcp,anthropic]", "asasked-mcp"],
      "env": {"CLAUDE_API_KEY": "your-key"}
    }
  }
}
```

Quit Claude Desktop completely and start it again. If the server does not
appear, use the full path to `uvx` (see above); the logs are in
`~/Library/Logs/Claude/mcp-server-asasked.log` on macOS.

### Cursor

`~/.cursor/mcp.json` for every project, or `.cursor/mcp.json` in one:

```json
{
  "mcpServers": {
    "asasked": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "asasked[mcp,anthropic]", "asasked-mcp"],
      "env": {"CLAUDE_API_KEY": "${env:CLAUDE_API_KEY}"}
    }
  }
}
```

### VS Code (Copilot agent mode)

`.vscode/mcp.json` in a project. VS Code asks for the key the first time
the server starts and keeps it out of the file:

```json
{
  "inputs": [
    {"type": "promptString", "id": "claude-key", "description": "Claude API key", "password": true}
  ],
  "servers": {
    "asasked": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "asasked[mcp,anthropic]", "asasked-mcp"],
      "env": {"CLAUDE_API_KEY": "${input:claude-key}"}
    }
  }
}
```

### OpenAI Codex CLI

```bash
codex mcp add asasked --env CLAUDE_API_KEY=your-key -- uvx --from "asasked[mcp,anthropic]" asasked-mcp
```

Or in `~/.codex/config.toml`, passing the key through from your
environment:

```toml
[mcp_servers.asasked]
command = "uvx"
args = ["--from", "asasked[mcp,anthropic]", "asasked-mcp"]
env_vars = ["CLAUDE_API_KEY"]
```

### Gemini CLI

In `~/.gemini/settings.json` (or `.gemini/settings.json` in a project):

```json
{
  "mcpServers": {
    "asasked": {
      "command": "uvx",
      "args": ["--from", "asasked[mcp]", "asasked-mcp"],
      "env": {"LLM_API_KEY": "$LLM_API_KEY"}
    }
  }
}
```

### Any other MCP app

Most apps take the same three things: the command (`uvx`, or the full path
to `asasked-mcp`), the arguments (`--from`, `asasked[mcp,anthropic]`,
`asasked-mcp`, or none) and the key as an environment variable.

### Checking that it works

Ask the agent something like: *"I asked for black sneakers in size 42. The
cart has white sneakers in size 42 for $50. Check the order with
check_order."* It should come back with *ask* and a question about the
colour. If it answers *ask* with "I couldn't automatically check this
order", the server runs but has no working key.

## Agent frameworks in Python

If payment goes through your own code, put the guard there: the agent then
cannot pay around it. The hooks for Claude Agent SDK, OpenAI Agents SDK and
LangChain, and `guard.protect(checkout)` for anything else, are described in
[the README](../README.md#the-pre-checkout-guard).
