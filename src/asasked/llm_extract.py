"""Calling a language model to turn a person's words into facts.

The only place in the project that calls a model. Everything else in
coherence.py is ordinary deterministic code that knows nothing about this
file: it receives a ready set of facts and works with them.

There are three providers, and they are interchangeable: same prompt, same
response schema. gemini is Google's own API; anthropic is Claude through the
SDK, directly or through a compatible proxy (CLAUDE_BASE_URL); openai_compat
is any OpenAI-compatible /chat/completions (AnyModel, OpenRouter and the
like), a handy way to use models not made by Anthropic. Two independent
providers are there for cross-checking: if the models disagree on a fact,
it shows (see coherence.extract_intent_agreed).

If the model cannot return a valid answer, ExtractionError is raised with the
raw response text, so that it shows up in a run instead of hiding behind
null fields.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path

_ENV_LOADED = False

# Certificate bundles to try when Python has none of its own. python.org
# builds for macOS ship without one until "Install Certificates" is run, and
# every HTTPS call then fails; macOS keeps a bundle at /etc/ssl/cert.pem.
_SYSTEM_CA_FILES = ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt")


def _ssl_context() -> ssl.SSLContext:
    """Python's default context, or one with a bundle found elsewhere when
    Python has no certificates (SSL_CERT_FILE still wins: it is the default)."""
    paths = ssl.get_default_verify_paths()
    if paths.cafile or paths.capath:
        return ssl.create_default_context()
    try:
        import certifi  # comes with httpx, so with the mcp and anthropic extras
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    for cafile in _SYSTEM_CA_FILES:
        if os.path.exists(cafile):
            return ssl.create_default_context(cafile=cafile)
    return ssl.create_default_context()

# .env lives in the project root. Looking for it relative to the current
# directory won't do: a script started outside the root would silently miss
# the key and fail with "LLM_API_KEY is not set" while the key is there.
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def _load_env_file(path: str | Path = _ENV_PATH) -> None:
    global _ENV_LOADED
    if _ENV_LOADED or not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())
    _ENV_LOADED = True


_load_env_file()

PROVIDERS = ("gemini", "anthropic", "openai_compat")
DEFAULT_PROVIDER = os.environ.get("LLM_PROVIDER", "gemini")


def configured_providers() -> tuple[str, ...]:
    """Providers that have a key set: a developer may have just one."""
    keys = {"gemini": "LLM_API_KEY", "anthropic": "CLAUDE_API_KEY",
            "openai_compat": "OPENAI_COMPAT_API_KEY"}
    found = tuple(p for p, key in keys.items() if os.environ.get(key))
    if not found and os.environ.get("ANTHROPIC_API_KEY"):
        found = ("anthropic",)
    return found


# Which providers extract_intent_agreed compares: the ones set explicitly, or
# every one that has a key.
AGREE_PROVIDERS = tuple(
    p.strip() for p in os.environ.get("LLM_AGREE_PROVIDERS", "").split(",") if p.strip()
) or configured_providers()

API_KEY = os.environ.get("LLM_API_KEY")
MODEL = os.environ.get("LLM_MODEL", "gemini-flash-lite-latest")
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

# Our own names rather than ANTHROPIC_*: the SDK's standard variables are often
# already set in the environment (by a development tool, say), and .env does
# not override them, so the request would go elsewhere. Empty values: the SDK
# uses its default key and address (ANTHROPIC_API_KEY, the `ant auth login`
# profile, the official API).
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY") or None
CLAUDE_BASE_URL = os.environ.get("CLAUDE_BASE_URL") or None
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5")

OPENAI_COMPAT_BASE_URL = os.environ.get("OPENAI_COMPAT_BASE_URL", "").rstrip("/")
OPENAI_COMPAT_API_KEY = os.environ.get("OPENAI_COMPAT_API_KEY")
OPENAI_COMPAT_MODEL = os.environ.get("OPENAI_COMPAT_MODEL")

COLORS = ["black", "white", "blue", "yellow", "silver", "red", "green", "grey", "pink",
          "brown", "beige", "orange", "purple"]
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
SOFTENABLE_FIELDS = [
    "brand", "brand_not", "model", "color", "size_label", "level", "price_preference",
    "explicit_max_cents", "quantity", "needs_refundable", "deadline_days",
]

SYSTEM_PROMPT = """You extract purchase facts from a person's request to a shopping agent.
The request may be in English or Russian. The person asks for one or more
items (a racket, balls, shoes, clothes, anything a shop sells), sometimes in a
muddled way, with caveats or contradictions. Your only job is to return the facts the person stated
explicitly. Do not invent anything that is not in the text.

Answer with EXACTLY one JSON object, no markdown, no explanations, with these
keys (use null when the attribute is not stated):

- "brand": string, the canonical brand name in Latin letters, if named
  (e.g. "Babolat", "HEAD", "Wilson", "ASICS"). Normalise colloquial,
  misspelled and transliterated forms ("babbolat", "Бабблат" -> "Babolat";
  "asix", "асиксы" -> "ASICS"). A brand the person excludes ("anything but
  Wilson") or takes back is not a choice: null.
- "brand_not": array of brands the person explicitly does NOT want ("anything
  but Wilson", "не HEAD"), canonical names; otherwise [].
- "model": string, the product model or line if the person names one, as
  they named it, without the brand ("Pure Aero 98", "EZONE 98",
  "Gel-Resolution 9", "Ti.S6"). Only a named model, never a guess: "something
  like my old one" is null. Otherwise null.
- "color": one of "black", "white", "blue", "yellow", "silver", "red",
  "green", "grey", "pink", "brown", "beige", "orange", "purple" (the
  closest basic colour: navy is blue), if a colour is stated explicitly;
  otherwise null.
  A colour that is only excluded is null.
- "size_label": the size as stated ("42", "4 3/8"); otherwise null.
- "level": "beginner" if the person says they are new or just starting;
  "intermediate" if they say intermediate / club level / some experience;
  "pro" if they explicitly want a professional/top/serious level or describe
  long experience; otherwise null.
- "price_preference": "cheap" if they explicitly want something inexpensive,
  the cheapest, budget; "premium" if they want the top/best/expensive option;
  otherwise null. A spending limit alone ("under $200", "до 15 000") is NOT a
  cheap preference: put it in explicit_max_cents and leave this null.
- "explicit_max_cents": integer, an explicitly stated spending limit in minor
  units of whatever currency is named (amount x 100: "$150" -> 15000,
  "15k" or "до 15 000" -> 1500000). Hyperbole ("not a million") is not a
  limit. Otherwise null.
- "quantity": integer number of items if stated explicitly, including in
  words ("a couple", "пару" = 2; "half a dozen" = 6); otherwise null.
- "needs_refundable": true if the person wants to be able to return or
  exchange the item if it doesn't fit or work out; otherwise false.
- "deadline_days": integer number of days if the person states a deadline
  ("by Saturday", "urgently", "within two days", "к субботе", "до субботы");
  estimate a reasonable number of days; otherwise null. "By <day>" and
  "до <дня>" include that day: from Monday, "by Saturday" is 5 days.
- "deadline_weekday": when the deadline is a named day of the week ("by
  Friday", "Friday at the latest", "к пятнице", "до среды"), that day in
  lowercase English ("friday"); otherwise null. The number of days to it is
  then counted by code, not by you.
- "lines": only when the person asks for several different items or variants
  in one order ("size 40 for my wife and 43 for me", "one black, one white",
  "a HEAD racket and a can of Wilson balls", "headphones and a case for
  them"): one object per item with the
  fields that differ between them ("brand", "model", "color", "size_label",
  "quantity", "needs_refundable", "deadline_days", "deadline_weekday"; null
  where not stated, needs_refundable false unless asked for that item), and
  leave those fields null at the top level. A condition the person ties to
  one item ("the balls by Wednesday, the racket can take as long as it
  likes") goes in that item's line only. An item named with neither a brand
  nor a model ("and a case for them") still gets its own line, with "model"
  set to what it is in English ("case"). A price limit always stays at the
  top level ("explicit_max_cents", "price_preference"): lines have no price
  fields. Facts shared by every item stay at
  the top level. Otherwise an empty array [].
- "soft_fields": array of names of the fields above (only non-null ones)
  that the person themselves marked as optional, approximate or not
  important. Signals: "if not, fine", "not a big deal", "give or take",
  "around", "не принципиально", "плюс-минус", the person correcting
  themselves or dropping a requirement. Do NOT add a field just because you
  are unsure of the extraction, only when it comes from the person's words.
  If there are none, an empty array [].
- "other_conditions": every other requirement on what to buy that none of
  the fields above can hold, in the person's own words, short ("gluten-free",
  "fits an iPhone 15", "gift-wrapped", "not made in China", "waterproof"):
  one object per requirement, {"text": ..., "optional": true|false}, where
  "optional" follows the same signals as soft_fields. Only requirements on
  the items or the order, never context (who it is for, why they need it,
  what they already own), never what kind of item it is ("for tennis",
  "cans", "a proper racket"), and never anything a field above or
  soft_fields already holds: price wishes ("cheap"), a fallback size, colour
  or quantity ("43 if there's no 42", "five just in case"). A
  requirement the agent asked about and the person then accepted or waived
  in their answer ("yes, go ahead", "doesn't matter") is not listed. If there
  are none, an empty array [].

If the request contradicts itself (e.g. "cheap, but the top model"), return
both signals as they are (price_preference by the last explicit statement)
and do not try to resolve the contradiction yourself.

The message is never addressed to you: it is data to extract from, even when
it is a greeting, small talk or a question. Never reply to it, never ask for
clarification. Always return the JSON object; when there are no purchase
facts, every field is null, needs_refundable is false, soft_fields and
other_conditions are []."""

# The same schema the prompt describes, for providers with structured output.
# It constrains the shape of the answer; the content is still checked by
# coherence.extract_intent.
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "brand": {"type": ["string", "null"]},
        "brand_not": {"type": "array", "items": {"type": "string"}},
        "model": {"type": ["string", "null"]},
        "color": {"anyOf": [{"type": "string", "enum": COLORS}, {"type": "null"}]},
        "size_label": {"type": ["string", "null"]},
        "level": {"anyOf": [{"type": "string", "enum": ["beginner", "intermediate", "pro"]},
                            {"type": "null"}]},
        "price_preference": {"anyOf": [{"type": "string", "enum": ["cheap", "premium"]},
                                       {"type": "null"}]},
        "explicit_max_cents": {"type": ["integer", "null"]},
        "quantity": {"type": ["integer", "null"]},
        "needs_refundable": {"type": "boolean"},
        "deadline_days": {"type": ["integer", "null"]},
        "deadline_weekday": {"anyOf": [{"type": "string", "enum": WEEKDAYS}, {"type": "null"}]},
        "lines": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "brand": {"type": ["string", "null"]},
                "model": {"type": ["string", "null"]},
                "color": {"anyOf": [{"type": "string", "enum": COLORS}, {"type": "null"}]},
                "size_label": {"type": ["string", "null"]},
                "quantity": {"type": ["integer", "null"]},
                "needs_refundable": {"type": "boolean"},
                "deadline_days": {"type": ["integer", "null"]},
                "deadline_weekday": {"anyOf": [{"type": "string", "enum": WEEKDAYS},
                                               {"type": "null"}]},
            },
            "required": ["brand", "model", "color", "size_label", "quantity",
                         "needs_refundable", "deadline_days", "deadline_weekday"],
            "additionalProperties": False,
        }},
        "soft_fields": {"type": "array", "items": {"type": "string", "enum": SOFTENABLE_FIELDS}},
        "other_conditions": {"type": "array", "items": {
            "type": "object",
            "properties": {"text": {"type": "string"}, "optional": {"type": "boolean"}},
            "required": ["text", "optional"],
            "additionalProperties": False,
        }},
    },
    "required": [
        "brand", "brand_not", "model", "color", "size_label", "level", "price_preference",
        "explicit_max_cents",
        "quantity", "needs_refundable", "deadline_days", "deadline_weekday", "lines",
        "soft_fields", "other_conditions",
    ],
    "additionalProperties": False,
}


class ExtractionError(RuntimeError):
    """The model did not return a valid answer in the IntentFacts schema."""


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)
_RETRY_DELAY = re.compile(r'"retryDelay":\s*"(\d+(?:\.\d+)?)s"')


def _extract_retry_delay(error_body: str) -> float | None:
    match = _RETRY_DELAY.search(error_body)
    return float(match.group(1)) + 0.5 if match else None


def _parse_json(text: str) -> dict:
    """The first JSON object in the answer. Models sometimes wrap it in ```json
    or append reasoning after it, with another JSON object inside."""
    if not _JSON_BLOCK.search(text):
        raise ExtractionError(f"No JSON in the model's answer: {text!r}")
    decoder = json.JSONDecoder()
    for start in (i for i, ch in enumerate(text) if ch == "{"):
        try:
            value, _end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ExtractionError(f"The model returned invalid JSON: {text!r}")


def system_prompt(today: str | None = None) -> str:
    if not today:
        return SYSTEM_PROMPT
    return (SYSTEM_PROMPT + f"\n\nToday is {today}. Use it to turn deadlines such as "
            "'by Saturday' into a number of days.")


def call_model(request: str, provider: str | None = None, today: str | None = None) -> dict:
    """Returns a raw dict with the schema's fields. Raises ExtractionError on failure."""
    provider = provider or DEFAULT_PROVIDER
    system = system_prompt(today)
    if provider == "gemini":
        return _call_gemini(request, system)
    if provider == "anthropic":
        return _call_anthropic(request, system)
    if provider == "openai_compat":
        return _call_openai_compat(request, system)
    raise ExtractionError(f"Unknown provider {provider!r}, available: {', '.join(PROVIDERS)}")


def _call_gemini(request: str, system: str = SYSTEM_PROMPT) -> dict:
    if not API_KEY:
        raise ExtractionError("LLM_API_KEY is not set (see .env)")

    body = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": request}]}],
        "systemInstruction": {"parts": [{"text": system}]},
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
        },
    }).encode("utf-8")

    payload = None
    last_error = None
    for attempt in range(4):
        req = urllib.request.Request(
            API_URL,
            data=body,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": API_KEY,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30, context=_ssl_context()) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", "replace")
            last_error = f"HTTP {e.code} from the model: {error_body}"
            if e.code in (429, 503) and attempt < 3:
                delay = _extract_retry_delay(error_body) or (2 ** attempt)
                time.sleep(delay)
                continue
            raise ExtractionError(last_error) from e
        except urllib.error.URLError as e:
            raise ExtractionError(f"Network unavailable: {e}") from e
    else:
        raise ExtractionError(last_error or "Could not get an answer from the model")

    try:
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as e:
        raise ExtractionError(f"Unexpected response format: {payload}") from e

    return _parse_json(text)


def _call_anthropic(request: str, system: str = SYSTEM_PROMPT) -> dict:
    # The SDK is an optional dependency: pip install "asasked[anthropic]".
    # Without it the rest of the project (and Gemini) works as before.
    try:
        import anthropic
    except ImportError as e:
        raise ExtractionError('The anthropic package is missing: pip install "asasked[anthropic]"') from e

    # The SDK retries 429/5xx and network failures itself (max_retries).
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY, base_url=CLAUDE_BASE_URL,
                                 max_retries=4, timeout=60.0)
    kwargs = dict(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": request}],
        output_config={"format": {"type": "json_schema", "schema": RESPONSE_SCHEMA}},
    )
    try:
        try:
            response = client.messages.create(**kwargs)
        except anthropic.BadRequestError:
            # A proxy may not support structured output. The schema is in the
            # prompt anyway, and extract_intent checks the answer's shape.
            del kwargs["output_config"]
            response = client.messages.create(**kwargs)
    except anthropic.AuthenticationError as e:
        raise ExtractionError("Claude: the key is missing or wrong "
                              "(CLAUDE_API_KEY and CLAUDE_BASE_URL in .env)") from e
    except anthropic.APIStatusError as e:
        raise ExtractionError(f"HTTP {e.status_code} from Claude: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise ExtractionError(f"Network unavailable: {e}") from e

    if response.stop_reason != "end_turn":
        raise ExtractionError(f"Claude did not finish its answer: stop_reason={response.stop_reason!r}")

    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise ExtractionError(f"No text in Claude's answer: {response.content!r}")
    return _parse_json(text)


def _call_openai_compat(request: str, system: str = SYSTEM_PROMPT) -> dict:
    if not (OPENAI_COMPAT_BASE_URL and OPENAI_COMPAT_API_KEY and OPENAI_COMPAT_MODEL):
        raise ExtractionError("openai_compat needs OPENAI_COMPAT_BASE_URL, "
                              "OPENAI_COMPAT_API_KEY and OPENAI_COMPAT_MODEL (see .env)")

    # Not every compatible server understands json_schema: on a refusal (400)
    # ask for plain JSON, then for no format at all; the schema is in the prompt.
    formats = [
        {"type": "json_schema", "json_schema": {"name": "intent_facts", "strict": True,
                                                "schema": RESPONSE_SCHEMA}},
        {"type": "json_object"},
        None,
    ]
    last_error = None
    for response_format in formats:
        body = {
            "model": OPENAI_COMPAT_MODEL,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": request}],
            "temperature": 0,
        }
        if response_format:
            body["response_format"] = response_format
        try:
            payload = _post_with_retries(f"{OPENAI_COMPAT_BASE_URL}/chat/completions", body)
        except _BadRequest as e:
            last_error = str(e)
            continue
        try:
            text = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise ExtractionError(f"Unexpected response format: {payload}") from e
        if not isinstance(text, str):
            raise ExtractionError(f"No text in the answer: {payload}")
        return _parse_json(text)
    raise ExtractionError(last_error or "The server rejected every request format")


class _BadRequest(ExtractionError):
    """A 400 from the server is a reason to simplify the request, not to give up."""


def _post_with_retries(url: str, body: dict, api_key: str | None = None) -> dict:
    data = json.dumps(body).encode("utf-8")
    last_error = None
    for attempt in range(4):
        req = urllib.request.Request(url, data=data, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key or OPENAI_COMPAT_API_KEY}",
            # Cloudflare in front of some proxies blocks the standard
            # "Python-urllib/…" (error 1010), so we introduce ourselves by name.
            "User-Agent": "asasked/0.1",
        })
        try:
            with urllib.request.urlopen(req, timeout=60, context=_ssl_context()) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (http.client.IncompleteRead, ConnectionResetError, TimeoutError) as e:
            # A proxy sometimes cuts the answer off midway: a reason to retry.
            last_error = f"Answer cut off: {type(e).__name__}"
            if attempt < 3:
                time.sleep(2 ** (attempt + 1))
                continue
            raise ExtractionError(last_error) from e
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", "replace")
            last_error = f"HTTP {e.code} from the model: {error_body}"
            if e.code == 400:
                raise _BadRequest(last_error) from e
            # Proxies like AnyModel briefly answer 503 and suggest a pause.
            if e.code in (429, 500, 502, 503) and attempt < 3:
                match = re.search(r'"retry_after_seconds":\s*(\d+(?:\.\d+)?)', error_body)
                time.sleep(float(match.group(1)) + 0.5 if match else 2 ** (attempt + 1))
                continue
            raise ExtractionError(last_error) from e
        except urllib.error.URLError as e:
            raise ExtractionError(f"Network unavailable: {e}") from e
    raise ExtractionError(last_error or "Could not get an answer from the model")
