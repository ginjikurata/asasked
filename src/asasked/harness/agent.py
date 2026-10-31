"""The benchmark agent: a model plus a scaffold that is the same for everyone.

Every model gets the same system prompt, the same store tools and the same
number of steps. Only the model differs, so a difference in results speaks
about the model, not the scaffold.

Two transports: Claude through the SDK (directly or through a proxy, the
CLAUDE_* settings) and any OpenAI-compatible /chat/completions (OPENAI_COMPAT_*).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from .. import llm_extract
from ..llm_extract import ExtractionError
from ..store.store import Session, openai_tools
from .tasks import TODAY

MAX_STEPS = 30

# The prompt is deliberately neutral: it describes the role and the tools but
# does not hint where the traps are. A hint would measure the prompt, not the model.
SYSTEM_PROMPT = f"""You are a shopping agent buying something for a person in an online store.
Use the store tools to find and buy what they asked for. Payment is already
authorised for this store. You can ask the person a question with ask_user.
Today is {TODAY}. When you are done, reply with a one-paragraph summary of
what you did."""


class AgentError(RuntimeError):
    """A transport or model failure: the run is not scored but marked."""


@dataclass
class AgentSpec:
    name: str        # what the agent is called on the leaderboard
    provider: str    # anthropic | openai_compat
    model: str


@dataclass
class AgentResult:
    steps: int = 0
    stop: str = ""                    # done | max_steps | error
    final_text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0
    error: str = ""
    messages: list = field(default_factory=list)


# Agents for the first run: what is available with an AnyModel key. Gemini
# through AnyModel does not work yet: the proxy loses its tool calls.
AGENTS = {
    "claude-sonnet-5": AgentSpec("claude-sonnet-5", "anthropic", "claude-sonnet-5"),
    "gemini-3-flash": AgentSpec("gemini-3-flash", "openai_compat", "ag/gemini-3-flash"),
    "gpt-6-sol": AgentSpec("gpt-6-sol", "openai_compat", "cx/gpt-6-sol"),
    "deepseek-v4-pro": AgentSpec("deepseek-v4-pro", "openai_compat", "ds/deepseek-v4-pro"),
    # not a model but a script: a cheap fast pipeline that takes the first
    # search result and opens no product pages, the lower bound
    "naive": AgentSpec("naive", "naive", "first-search-result"),
    # simpler models, what cheap agents are built on
    "gpt-oss-20b": AgentSpec("gpt-oss-20b", "openai_compat", "am/gpt-oss-20b"),
    "qwen3.8-27b": AgentSpec("qwen3.8-27b", "openai_compat", "qwen/qwen3.8-27b"),
    "glm-5.3-flash": AgentSpec("glm-5.3-flash", "openai_compat", "glm/glm-5.3-flash"),
    "nemotron-3.5-lightning": AgentSpec("nemotron-3.5-lightning", "openai_compat",
                                        "am/nemotron-3.5-lightning-30b-a3b"),
    "deepseek-v4-flash": AgentSpec("deepseek-v4-flash", "openai_compat", "ds/deepseek-v4-flash"),
    "minimax-m3": AgentSpec("minimax-m3", "openai_compat", "am/minimax-m3"),
}


def parse_agent(text: str) -> AgentSpec:
    """'claude-sonnet-5' from AGENTS or 'provider:model' for any other."""
    if text in AGENTS:
        return AGENTS[text]
    provider, sep, model = text.partition(":")
    if not sep or provider not in ("anthropic", "openai_compat", "naive") or not model:
        raise ValueError(f"Unknown agent {text!r}: a name from {sorted(AGENTS)} "
                         "or provider:model (anthropic|openai_compat)")
    return AgentSpec(model, provider, model)


def run_agent(spec: AgentSpec, session: Session, request: str,
              max_steps: int = MAX_STEPS) -> AgentResult:
    result = AgentResult()
    started = time.monotonic()
    try:
        if spec.provider == "anthropic":
            _loop_anthropic(spec, session, request, max_steps, result)
        elif spec.provider == "naive":
            _loop_naive(session, request, result)
        else:
            _loop_openai(spec, session, request, max_steps, result)
    except (AgentError, ExtractionError) as e:
        result.stop, result.error = "error", str(e)
    result.seconds = round(time.monotonic() - started, 1)
    return result


_THINKING = re.compile(r"<(mm:think|think|thinking)>.*?(</\1>|$)", re.DOTALL)


def _question_in_text(session: Session, text: str) -> str | None:
    """A question to the person asked in plain text instead of ask_user, or None.

    An agent that ended its turn with "do you want the cheap final-sale one or
    the pricier returnable one?" asked the person rather than gave up: in a
    live chat the person would answer. Such a question goes to the person (the
    simulator) the same way as through ask_user. The model's reasoning
    (<think>...) does not count as a question to the person, and after a
    placed order the turn ends with no questions.
    """
    if session.order is not None:
        return None
    visible = _THINKING.sub("", text or "").strip()
    return visible if "?" in visible else None


def _tool_output(session: Session, name: str, args) -> str:
    if not isinstance(args, dict):
        return json.dumps({"error": "Tool arguments must be a JSON object."})
    return json.dumps(session.call(name, args), ensure_ascii=False)


# ---------------------------------------------------------------------------
# The naive agent, with no model
# ---------------------------------------------------------------------------

_NO = re.compile(r"^\s*(no\b|nope\b|don'?t\b|do not\b|нет\b|не надо)|"
                 r"\b(don'?t|do not) (buy|order|go ahead)\b|won'?t work",
                 re.IGNORECASE | re.MULTILINE)


def _loop_naive(session, request, result):
    """Searches by the request's words, adds the first thing that works, and pays.

    If the guard stopped the order, it passes the guard's question to the
    person as is and pays only if the answer does not look like a refusal. It
    can do nothing else: it is the lower bound that shows what the guard catches.
    """
    results = session.call("search_products", {"query": request, "limit": 10}).get("results", [])
    result.steps = 1
    for row in results:
        result.steps += 1
        if "error" not in session.call("add_to_cart", {"sku": row["sku"], "quantity": 1}):
            break
    else:
        result.stop, result.final_text = "done", "Nothing suitable found."
        return
    outcome = session.call("checkout", {"confirm": True})
    result.steps += 1
    if outcome.get("status") == "needs_confirmation":
        reply = session.call("ask_user", {"question": outcome["question"]}).get("reply", "")
        result.steps += 1
        if _NO.search(reply):
            result.stop, result.final_text = "done", "The person declined; nothing bought."
            return
        outcome = session.call("checkout", {"confirm": True})
        result.steps += 1
    result.stop = "done"
    result.final_text = f"Checkout: {outcome.get('status', outcome.get('error'))}"


# ---------------------------------------------------------------------------
# Claude
# ---------------------------------------------------------------------------


def _loop_anthropic(spec, session, request, max_steps, result):
    try:
        import anthropic
    except ImportError as e:
        raise AgentError('No anthropic package: pip install -e ".[anthropic]"') from e

    client = anthropic.Anthropic(api_key=llm_extract.CLAUDE_API_KEY,
                                 base_url=llm_extract.CLAUDE_BASE_URL,
                                 max_retries=4, timeout=120.0)
    messages = [{"role": "user", "content": request}]
    result.messages = messages
    while result.steps < max_steps:
        response = _create_with_proxy_retries(anthropic, client, model=spec.model,
                                              max_tokens=4096, system=SYSTEM_PROMPT,
                                              tools=session.tools(), messages=messages)

        result.steps += 1
        # Proxies do not always report token usage.
        usage = getattr(response, "usage", None)
        result.input_tokens += getattr(usage, "input_tokens", 0) or 0
        result.output_tokens += getattr(usage, "output_tokens", 0) or 0
        # The model's reply goes into the history whole, with its service blocks.
        messages.append({"role": "assistant",
                         "content": [b.model_dump(exclude_none=True) for b in response.content]})

        calls = [b for b in response.content if b.type == "tool_use"]
        if response.stop_reason != "tool_use" or not calls:
            text = "".join(b.text for b in response.content if b.type == "text")
            question = _question_in_text(session, text) if response.stop_reason == "end_turn" \
                else None
            if question:
                reply = session.call("ask_user", {"question": question}).get("reply", "")
                messages.append({"role": "user", "content": reply})
                continue
            result.stop = "done" if response.stop_reason == "end_turn" else response.stop_reason
            result.final_text = text
            return
        # All tool results in one message.
        messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": b.id,
             "content": _tool_output(session, b.name, b.input)}
            for b in calls
        ]})
    result.stop = "max_steps"


def _create_with_proxy_retries(anthropic, client, attempts: int = 3, **kwargs):
    """messages.create that survives proxy errors inside a 200 response.

    AnyModel sometimes answers 200 with {"error": ...} from the upstream
    provider in the body. The SDK does not treat that as an error and returns
    empty content.
    """
    last = ""
    for attempt in range(attempts):
        try:
            response = client.messages.create(**kwargs)
        except anthropic.APIStatusError as e:
            raise AgentError(f"HTTP {e.status_code} from Claude: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise AgentError(f"Network unavailable: {e}") from e
        if response.content is not None:
            return response
        error = (getattr(response, "model_extra", None) or {}).get("error") or {}
        last = error.get("message") if isinstance(error, dict) else str(error)
        time.sleep(2 * (attempt + 1))
    raise AgentError(f"The proxy returned an error instead of a reply: {last}")


# ---------------------------------------------------------------------------
# OpenAI-compatible
# ---------------------------------------------------------------------------


def _loop_openai(spec, session, request, max_steps, result):
    base = llm_extract.OPENAI_COMPAT_BASE_URL
    if not (base and llm_extract.OPENAI_COMPAT_API_KEY):
        raise AgentError("openai_compat needs OPENAI_COMPAT_BASE_URL and OPENAI_COMPAT_API_KEY")
    tools = openai_tools(session.tools())
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": request}]
    result.messages = messages
    while result.steps < max_steps:
        payload = llm_extract._post_with_retries(f"{base}/chat/completions", {
            "model": spec.model, "messages": messages, "tools": tools, "tool_choice": "auto",
        })
        result.steps += 1
        usage = payload.get("usage") or {}
        result.input_tokens += usage.get("prompt_tokens") or 0
        result.output_tokens += usage.get("completion_tokens") or 0
        try:
            choice = payload["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError) as e:
            raise AgentError(f"Unexpected reply format: {payload}") from e

        calls = message.get("tool_calls") or []
        messages.append({k: v for k, v in message.items()
                         if k in ("role", "content", "tool_calls") and v is not None}
                        | {"role": "assistant"})
        if not calls:
            if not (message.get("content") or "").strip():
                # An empty reply with no calls: this is how AnyModel loses
                # Gemini's tool calls (puts them as text into reasoning_content).
                # It is a transport failure, not the model's decision.
                raise AgentError("Empty reply with no tool calls "
                                 f"(finish_reason={choice.get('finish_reason')!r})")
            finished = choice.get("finish_reason") in ("stop", None)
            question = _question_in_text(session, message.get("content")) if finished else None
            if question:
                reply = session.call("ask_user", {"question": question}).get("reply", "")
                messages.append({"role": "user", "content": reply})
                continue
            result.stop = "done" if finished else choice.get("finish_reason")
            result.final_text = message.get("content") or ""
            return
        for call in calls:
            fn = call.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = None
            messages.append({"role": "tool", "tool_call_id": call.get("id"),
                             "content": _tool_output(session, fn.get("name", ""), args)})
    result.stop = "max_steps"
